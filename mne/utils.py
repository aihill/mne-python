"""Some utility functions"""

# Authors: Alexandre Gramfort <gramfort@nmr.mgh.harvard.edu>
#
# License: BSD (3-clause)

import warnings
import numpy as np
import logging
from distutils.version import LooseVersion
import os
import os.path as op
from functools import wraps
import inspect
import subprocess
import sys
from sys import stdout
import tempfile
import time
import shutil
from shutil import rmtree
import atexit
from math import log
import json
import urllib
import urllib2
import ftplib
import urlparse
from scipy import linalg

logger = logging.getLogger('mne')


###############################################################################
# RANDOM UTILITIES

def check_random_state(seed):
    """Turn seed into a np.random.RandomState instance

    If seed is None, return the RandomState singleton used by np.random.
    If seed is an int, return a new RandomState instance seeded with seed.
    If seed is already a RandomState instance, return it.
    Otherwise raise ValueError.
    """
    if seed is None or seed is np.random:
        return np.random.mtrand._rand
    if isinstance(seed, (int, np.integer)):
        return np.random.RandomState(seed)
    if isinstance(seed, np.random.RandomState):
        return seed
    raise ValueError('%r cannot be used to seed a numpy.random.RandomState'
                     ' instance' % seed)


def split_list(l, n):
    """split list in n (approx) equal pieces"""
    n = int(n)
    sz = len(l) / n
    for i in range(n - 1):
        yield l[i * sz:(i + 1) * sz]
    yield l[(n - 1) * sz:]


class WrapStdOut(object):
    """Ridiculous class to work around how doctest captures stdout"""
    def __getattr__(self, name):
        # Even more ridiculous than this class, this must be sys.stdout (not
        # just stdout) in order for this to work (tested on OSX and Linux)
        return getattr(sys.stdout, name)


class _TempDir(str):
    """Class for creating and auto-destroying temp dir

    This is designed to be used with testing modules.

    We cannot simply use __del__() method for cleanup here because the rmtree
    function may be cleaned up before this object, so we use the atexit module
    instead. Passing del_after and print_del kwargs to the constructor are
    helpful primarily for debugging purposes.
    """
    def __new__(self, del_after=True, print_del=False):
        new = str.__new__(self, tempfile.mkdtemp())
        self._del_after = del_after
        self._print_del = print_del
        return new

    def __init__(self):
        self._path = self.__str__()
        atexit.register(self.cleanup)

    def cleanup(self):
        if self._del_after is True:
            if self._print_del is True:
                print 'Deleting %s ...' % self._path
            rmtree(self._path, ignore_errors=True)


def estimate_rank(data, tol=1e-4, return_singular=False,
                  copy=True):
    """Helper to estimate the rank of data

    This function will normalize the rows of the data (typically
    channels or vertices) such that non-zero singular values
    should be close to one.

    Parameters
    ----------
    tstart : float
        Start time to use for rank estimation. Defaul is 0.0.
    tstop : float | None
        End time to use for rank estimation. Default is 30.0.
        If None, the end time of the raw file is used.
    tol : float
        Tolerance for singular values to consider non-zero in
        calculating the rank. The singular values are calculated
        in this method such that independent data are expected to
        have singular value around one.
    return_singular : bool
        If True, also return the singular values that were used
        to determine the rank.
    copy : bool
        If False, values in data will be modified in-place during
        rank estimation (saves memory).

    Returns
    -------
    rank : int
        Estimated rank of the data.
    s : array
        If return_singular is True, the singular values that were
        thresholded to determine the rank are also returned.

    """
    if copy is True:
        data = data.copy()
    norms = np.sqrt(np.sum(data ** 2, axis=1))
    norms[norms == 0] = 1.0
    data /= norms[:, np.newaxis]
    s = linalg.svd(data, compute_uv=False, overwrite_a=True)
    rank = np.sum(s >= tol)
    if return_singular is True:
        return rank, s
    else:
        return rank


def run_subprocess(command, *args, **kwargs):
    """Run command using subprocess.Popen

    Run command and wait for command to complete. If the return code was zero
    then return, otherwise raise CalledProcessError.
    By default, this will also add stdout= and stderr=subproces.PIPE
    to the call to Popen to suppress printing to the terminal.

    Parameters
    ----------
    command : list of str
        Command to run as subprocess (see subprocess.Popen documentation).
    *args, **kwargs : arguments
        Arguments to pass to subprocess.Popen.

    Returns
    -------
    stdout : str
        Stdout returned by the process.
    stderr : str
        Stderr returned by the process.
    """
    if 'stderr' not in kwargs:
        kwargs['stderr'] = subprocess.PIPE
    if 'stdout' not in kwargs:
        kwargs['stdout'] = subprocess.PIPE

    # Check the PATH environment variable. If run_subprocess() is to be called
    # frequently this should be refactored so as to only check the path once.
    env = kwargs.get('env', os.environ)
    if any(p.startswith('~') for p in env['PATH'].split(os.pathsep)):
        msg = ("Your PATH environment variable contains at least one path "
               "starting with a tilde ('~') character. Such paths are not "
               "interpreted correctly from within Python. It is recommended "
               "that you use '$HOME' instead of '~'.")
        warnings.warn(msg)

    logger.info("Running subprocess: %s" % str(command))
    p = subprocess.Popen(command, *args, **kwargs)
    stdout, stderr = p.communicate()

    if stdout.strip():
        logger.info("stdout:\n%s" % stdout)
    if stderr.strip():
        logger.info("stderr:\n%s" % stderr)

    output = (stdout, stderr)
    if p.returncode:
        raise subprocess.CalledProcessError(p.returncode, command, output)

    return output

###############################################################################
# DECORATORS

# Following deprecated class copied from scikit-learn

# force show of DeprecationWarning even on python 2.7
warnings.simplefilter('default')


class deprecated(object):
    """Decorator to mark a function or class as deprecated.

    Issue a warning when the function is called/the class is instantiated and
    adds a warning to the docstring.

    The optional extra argument will be appended to the deprecation message
    and the docstring. Note: to use this with the default value for extra, put
    in an empty of parentheses:

    >>> from mne.utils import deprecated_func
    >>> deprecated() # doctest: +ELLIPSIS
    <mne.utils.deprecated object at ...>

    >>> @deprecated()
    ... def some_function(): pass
    """

    # Adapted from http://wiki.python.org/moin/PythonDecoratorLibrary,
    # but with many changes.

    # scikit-learn will not import on all platforms b/c it can be
    # sklearn or scikits.learn, so a self-contained example is used above

    def __init__(self, extra=''):
        """
        Parameters
        ----------
        extra: string
          to be added to the deprecation messages

        """
        self.extra = extra

    def __call__(self, obj):
        if isinstance(obj, type):
            return self._decorate_class(obj)
        else:
            return self._decorate_fun(obj)

    def _decorate_class(self, cls):
        msg = "Class %s is deprecated" % cls.__name__
        if self.extra:
            msg += "; %s" % self.extra

        # FIXME: we should probably reset __new__ for full generality
        init = cls.__init__

        def wrapped(*args, **kwargs):
            warnings.warn(msg, category=DeprecationWarning)
            return init(*args, **kwargs)
        cls.__init__ = wrapped

        wrapped.__name__ = '__init__'
        wrapped.__doc__ = self._update_doc(init.__doc__)
        wrapped.deprecated_original = init

        return cls

    def _decorate_fun(self, fun):
        """Decorate function fun"""

        msg = "Function %s is deprecated" % fun.__name__
        if self.extra:
            msg += "; %s" % self.extra

        def wrapped(*args, **kwargs):
            warnings.warn(msg, category=DeprecationWarning)
            return fun(*args, **kwargs)

        wrapped.__name__ = fun.__name__
        wrapped.__dict__ = fun.__dict__
        wrapped.__doc__ = self._update_doc(fun.__doc__)

        return wrapped

    def _update_doc(self, olddoc):
        newdoc = "DEPRECATED"
        if self.extra:
            newdoc = "%s: %s" % (newdoc, self.extra)
        if olddoc:
            newdoc = "%s\n\n%s" % (newdoc, olddoc)
        return newdoc


@deprecated
def deprecated_func():
    pass


def verbose(function):
    """Decorator to allow functions to override default log level

    Do not call this function directly to set the global verbosity level,
    instead use set_log_level().

    Parameters (to decorated function)
    ----------------------------------
    verbose : bool, str, int, or None
        The level of messages to print. If a str, it can be either DEBUG,
        INFO, WARNING, ERROR, or CRITICAL. Note that these are for
        convenience and are equivalent to passing in logging.DEBUG, etc.
        For bool, True is the same as 'INFO', False is the same as 'WARNING'.
        None defaults to using the current log level [e.g., set using
        mne.set_log_level()].
    """
    arg_names = inspect.getargspec(function).args
    # this wrap allows decorated functions to be pickled (e.g., for parallel)

    @wraps(function)
    def dec(*args, **kwargs):
        # Check if the first arg is "self", if it has verbose, make it default
        if len(arg_names) > 0 and arg_names[0] == 'self':
            default_level = getattr(args[0], 'verbose', None)
        else:
            default_level = None
        verbose_level = kwargs.get('verbose', default_level)
        if verbose_level is not None:
            old_level = set_log_level(verbose_level, True)
            # set it back if we get an exception
            try:
                ret = function(*args, **kwargs)
            except:
                set_log_level(old_level)
                raise
            set_log_level(old_level)
            return ret
        else:
            return function(*args, **kwargs)

    # set __wrapped__ attribute so ?? in IPython gets the right source
    dec.__wrapped__ = function

    return dec


def has_command_line_tools():
    if 'MNE_ROOT' not in os.environ:
        return False
    else:
        return True


requires_mne = np.testing.dec.skipif(not has_command_line_tools(),
                                     'Requires MNE command line tools')


def has_nibabel():
    try:
        import nibabel
        return True
    except ImportError:
        return False


def has_freesurfer():
    if not 'FREESURFER_HOME' in os.environ:
        return False
    else:
        return True


requires_fs_or_nibabel = np.testing.dec.skipif(not has_nibabel() and
                                               not has_freesurfer(),
                                               'Requires nibabel or '
                                               'Freesurfer')
requires_nibabel = np.testing.dec.skipif(not has_nibabel(),
                                         'Requires nibabel')
requires_freesurfer = np.testing.dec.skipif(not has_freesurfer(),
                                            'Requires Freesurfer')


def requires_pandas(function):
    """Decorator to skip test if pandas is not available"""
    @wraps(function)
    def dec(*args, **kwargs):
        skip = False
        try:
            import pandas
            version = LooseVersion(pandas.__version__)
            if version < '0.7.3':
                skip = True
        except ImportError:
            skip = True

        if skip is True:
            from nose.plugins.skip import SkipTest
            raise SkipTest('Test %s skipped, requires pandas'
                           % function.__name__)
        ret = function(*args, **kwargs)

        return ret

    return dec


def make_skipper_dec(module, skip_str):
    """Helper to make skipping decorators"""
    skip = False
    try:
        __import__(module)
    except ImportError:
        skip = True
    return np.testing.dec.skipif(skip, skip_str)


requires_sklearn = make_skipper_dec('sklearn', 'scikit-learn not installed')
requires_nitime = make_skipper_dec('nitime', 'nitime not installed')


###############################################################################
# LOGGING

def set_log_level(verbose=None, return_old_level=False):
    """Convenience function for setting the logging level

    Parameters
    ----------
    verbose : bool, str, int, or None
        The verbosity of messages to print. If a str, it can be either DEBUG,
        INFO, WARNING, ERROR, or CRITICAL. Note that these are for
        convenience and are equivalent to passing in logging.DEBUG, etc.
        For bool, True is the same as 'INFO', False is the same as 'WARNING'.
        If None, the environment variable MNE_LOG_LEVEL is read, and if
        it doesn't exist, defaults to INFO.
    return_old_level : bool
        If True, return the old verbosity level.
    """
    if verbose is None:
        verbose = get_config('MNE_LOGGING_LEVEL', 'INFO')
    elif isinstance(verbose, bool):
        if verbose is True:
            verbose = 'INFO'
        else:
            verbose = 'WARNING'
    if isinstance(verbose, basestring):
        verbose = verbose.upper()
        logging_types = dict(DEBUG=logging.DEBUG, INFO=logging.INFO,
                             WARNING=logging.WARNING, ERROR=logging.ERROR,
                             CRITICAL=logging.CRITICAL)
        if not verbose in logging_types:
            raise ValueError('verbose must be of a valid type')
        verbose = logging_types[verbose]
    logger = logging.getLogger('mne')
    old_verbose = logger.level
    logger.setLevel(verbose)
    return (old_verbose if return_old_level else None)


def set_log_file(fname=None, output_format='%(message)s', overwrite=None):
    """Convenience function for setting the log to print to a file

    Parameters
    ----------
    fname : str, or None
        Filename of the log to print to. If None, stdout is used.
        To suppress log outputs, use set_log_level('WARN').
    output_format : str
        Format of the output messages. See the following for examples:
            http://docs.python.org/dev/howto/logging.html
        e.g., "%(asctime)s - %(levelname)s - %(message)s".
    overwrite : bool, or None
        Overwrite the log file (if it exists). Otherwise, statements
        will be appended to the log (default). None is the same as False,
        but additionally raises a warning to notify the user that log
        entries will be appended.
    """
    logger = logging.getLogger('mne')
    handlers = logger.handlers
    for h in handlers:
        if isinstance(h, logging.FileHandler):
            h.close()
        logger.removeHandler(h)
    if fname is not None:
        if op.isfile(fname) and overwrite is None:
            warnings.warn('Log entries will be appended to the file. Use '
                          'overwrite=False to avoid this message in the '
                          'future.')
        mode = 'w' if overwrite is True else 'a'
        lh = logging.FileHandler(fname, mode=mode)
    else:
        """ we should just be able to do:
                lh = logging.StreamHandler(sys.stdout)
            but because doctests uses some magic on stdout, we have to do this:
        """
        lh = logging.StreamHandler(WrapStdOut())

    lh.setFormatter(logging.Formatter(output_format))
    # actually add the stream handler
    logger.addHandler(lh)


###############################################################################
# CONFIG / PREFS

def get_subjects_dir(subjects_dir=None, raise_error=False):
    """Safely use subjects_dir input to return SUBJECTS_DIR

    Parameters
    ----------
    subjects_dir : str | None
        If a value is provided, return subjects_dir. Otherwise, look for
        SUBJECTS_DIR config and return the result.
    raise_error : bool
        If True, raise a KeyError if no value for SUBJECTS_DIR can be found
        (instead of returning None).

    Returns
    -------
    value : str | None
        The SUBJECTS_DIR value.
    """
    if subjects_dir is None:
        subjects_dir = get_config('SUBJECTS_DIR', raise_error=raise_error)
    return subjects_dir


def get_config_path():
    """Get path to standard mne-python config file

    Returns
    -------
    config_path : str
        The path to the mne-python configuration file. On windows, this
        will be '%APPDATA%\.mne\mne-python.json'. On every other
        system, this will be $HOME/.mne/mne-python.json.
    """

    # this has been checked on OSX64, Linux64, and Win32
    val = os.getenv('APPDATA' if 'nt' == os.name.lower() else 'HOME', None)
    if val is None:
        raise ValueError('mne-python config file path could '
                         'not be determined, please report this '
                         'error to mne-python developers')

    val = op.join(val, '.mne', 'mne-python.json')
    return val


# List the known configuration values
known_config_types = [
    'MNE_BROWSE_RAW_SIZE',
    'MNE_CUDA_IGNORE_PRECISION',
    'MNE_DATASETS_MEGSIM_PATH',
    'MNE_DATASETS_SAMPLE_PATH',
    'MNE_LOGGING_LEVEL',
    'MNE_USE_CUDA',
    'SUBJECTS_DIR',
    ]
# These allow for partial matches, e.g. 'MNE_STIM_CHANNEL_1' is okay key
known_config_wildcards = [
    'MNE_STIM_CHANNEL',
    ]


def get_config(key, default=None, raise_error=False):
    """Read mne(-python) preference from env, then mne-python config

    Parameters
    ----------
    key : str
        The preference key to look for. The os evironment is searched first,
        then the mne-python config file is parsed.
    default : str | None
        Value to return if the key is not found.
    raise_error : bool
        If True, raise an error if the key is not found (instead of returning
        default).

    Returns
    -------
    value : str | None
        The preference key value.
    """

    if not isinstance(key, basestring):
        raise ValueError('key must be a string')

    # first, check to see if key is in env
    if key in os.environ:
        return os.environ[key]

    # second, look for it in mne-python config file
    config_path = get_config_path()
    if not op.isfile(config_path):
        key_found = False
        val = default
    else:
        with open(config_path, 'r') as fid:
            config = json.load(fid)
        key_found = True if key in config else False
        val = config.get(key, default)

    if not key_found and raise_error is True:
        meth_1 = 'os.environ["%s"] = VALUE' % key
        meth_2 = 'mne.utils.set_config("%s", VALUE)' % key
        raise KeyError('Key "%s" not found in environment or in the '
                       'mne-python config file:\n%s\nTry either:\n'
                       '    %s\nfor a temporary solution, or:\n'
                       '    %s\nfor a permanent one. You can also '
                       'set the environment variable before '
                       'running python.'
                       % (key, config_path, meth_1, meth_2))
    return val


def set_config(key, value):
    """Set mne-python preference in config

    Parameters
    ----------
    key : str
        The preference key to set.
    value : str |  None
        The value to assign to the preference key. If None, the key is
        deleted.
    """

    if not isinstance(key, basestring):
        raise ValueError('key must be a string')
    # While JSON allow non-string types, we allow users to override config
    # settings using env, which are strings, so we enforce that here
    if not isinstance(value, basestring) and value is not None:
        raise ValueError('value must be a string or None')
    if not key in known_config_types and not \
            any(k in key for k in known_config_wildcards):
        warnings.warn('Setting non-standard config type: "%s"' % key)

    # Read all previous values
    config_path = get_config_path()
    if op.isfile(config_path):
        with open(config_path, 'r') as fid:
            config = json.load(fid)
    else:
        config = dict()
        logger.info('Attempting to create new mne-python configuration '
                    'file:\n%s' % config_path)
    if value is None:
        config.pop(key, None)
    else:
        config[key] = value

    # Write all values
    directory = op.split(config_path)[0]
    if not op.isdir(directory):
        os.mkdir(directory)
    with open(config_path, 'w') as fid:
        json.dump(config, fid, sort_keys=True, indent=0)


class ProgressBar(object):
    """Class for generating a command-line progressbar

    Parameters
    ----------
    max_value : number
        Maximum value of process (e.g. number of samples to process, bytes to
        download, etc.).
    mesg : str
        Message to include at end of progress bar
    max_chars : int
        Number of characters to use for progress bar (be sure to save some room
        for the message and % complete as well).
    progress_character : char
        Character in the progress bar that indicates the portion completed
    spinner : bool
        Show a spinner.  Useful for long-running processes that may not
        increment the progress bar very often.  This provides the user with
        feedback that the progress has not stalled.

    Example
    -------
    >>> progress = ProgressBar(13000)
    >>> progress.update(3000) # doctest: +SKIP
    [.........                               ] 23.07692 |
    >>> progress.update(6000) # doctest: +SKIP
    [..................                      ] 46.15385 |

    >>> progress = ProgressBar(13000, spinner=True)
    >>> progress.update(3000) # doctest: +SKIP
    [.........                               ] 23.07692 |
    >>> progress.update(6000) # doctest: +SKIP
    [..................                      ] 46.15385 /
    """

    spinner_symbols = ['|', '/', '-', '\\']
    template = '\r[{}{}] {:.05f} {} {}   '

    def __init__(self, initial_value, max_value, mesg='', max_chars=40,
                 progress_character='.', spinner=False):
        self.cur_value = initial_value
        self.max_value = float(max_value)
        self.mesg = mesg
        self.max_chars = max_chars
        self.progress_character = progress_character
        self.spinner = spinner
        self.spinner_index = 0
        self.n_spinner = len(self.spinner_symbols)

    def update(self, cur_value, mesg=None):
        """Update progressbar with current value of process

        Parameters
        ----------
        cur_value : number
            Current value of process.  Should be <= max_value (but this is not
            enforced).  The percent of the progressbar will be computed as
            (cur_value / max_value) * 100
        mesg : str
            Message to display to the right of the progressbar.  If None, the
            last message provided will be used.  To clear the current message,
            pass a null string, ''.
        """
        # Ensure floating-point division so we can get fractions of a percent
        # for the progressbar.
        self.cur_value = cur_value
        progress = float(self.cur_value) / self.max_value
        num_chars = int(progress * self.max_chars)
        num_left = self.max_chars - num_chars

        # Update the message
        if mesg is not None:
            self.mesg = mesg

        # The \r tells the cursor to return to the beginning of the line rather
        # than starting a new line.  This allows us to have a progressbar-style
        # display in the console window.
        bar = self.template.format(self.progress_character * num_chars,
                                   ' ' * num_left,
                                   progress * 100,
                                   self.spinner_symbols[self.spinner_index],
                                   self.mesg)
        sys.stdout.write(bar)
        # Increament the spinner
        if self.spinner:
            self.spinner_index = (self.spinner_index + 1) % self.n_spinner

        # Force a flush because sometimes when using bash scripts and pipes,
        # the output is not printed until after the program exits.
        sys.stdout.flush()

    def update_with_increment_value(self, increment_value, mesg=None):
        """Update progressbar with the value of the increment instead of the
        current value of process as in update()
        
        Parameters
        ----------
        increment_value : number
            Value of the increment of process.  The percent of the progressbar
            will be computed as 
            (self.initial_size + increment_value / max_value) * 100
        mesg : str
            Message to display to the right of the progressbar.  If None, the
            last message provided will be used.  To clear the current message,
        """
        self.cur_value += increment_value
        self.update(self.cur_value, mesg)


# Copied from NISL: https://github.com/nisl/tutorial/blob/master/nisl/datasets.py
def _chunk_read_(response, local_file, chunk_size=8192, report_hook=None,
                 initial_size=0, total_size=None, verbose=0):
    """Download a file chunk by chunk and show advancement

    Parameters
    ----------
    response: urllib.addinfourl
        Response to the download request in order to get file size

    local_file: file
        Hard disk file where data should be written

    chunk_size: integer, optional
        Size of downloaded chunks. Default: 8192

    report_hook: boolean
        Whether or not to show downloading advancement. Default: None

    initial_size: int, optional
        If resuming, indicate the initial size of the file

    Returns
    -------
    data: string
        The downloaded file.

    """
    if total_size is None:
        total_size = response.info().getheader('Content-Length').strip()
    try:
        total_size = int(total_size) + initial_size
    except Exception, e:
        if verbose > 0:
            print "Warning: total size could not be determined."
            if verbose > 1:
                print "Full stack trace: %s" % e
        total_size = None
    bytes_so_far = initial_size

    if report_hook:
        progress = ProgressBar(bytes_so_far, total_size, max_chars=40, 
                               spinner=True, mesg='downloading')
    t0 = time.time()
    while True:
        chunk = response.read(chunk_size)
        bytes_so_far += len(chunk)

        if not chunk:
            if report_hook:
                sys.stderr.write('\n')
            break

        local_file.write(chunk)
        if report_hook:
            progress.update(bytes_so_far)

    return


# Copied from NISL: https://github.com/nisl/tutorial/blob/master/nisl/datasets.py
def _fetch_file(url, data_dir, resume=True, overwrite=False, md5sum=None,
                verbose=0):
    """Load requested file, downloading it if needed or requested

    Parameters
    ----------
    urls: array of strings
        Contains the urls of files to be downloaded.

    data_dir: string, optional
        Path of the data directory. Used to force data storage in a specified
        location. Default: None

    resume: boolean, optional
        If true, try to resume partially downloaded files

    overwrite: boolean, optional
        If true and file already exists, delete it.

    md5sum: string, optional
        MD5 sum of the file. Checked if download of the file is required

    verbose: integer, optional
        Defines the level of verbosity of the output

    Returns
    -------
    files: array of string
        Absolute paths of downloaded files on disk

    Notes
    -----
    If, for any reason, the download procedure fails, all downloaded data are
    cleaned.
    """
    # Determine data path
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)

    file_name = os.path.basename(url)
    temp_file_name = file_name + ".part"
    full_name = os.path.join(data_dir, file_name)
    temp_full_name = os.path.join(data_dir, temp_file_name)
    if os.path.exists(full_name):
        if overwrite:
            os.remove(full_name)
        else:
            return full_name
    if os.path.exists(temp_full_name):
        if overwrite:
            os.remove(temp_full_name)
    t0 = time.time()
    local_file = None
    initial_size = 0
    try:
        # Download data
        print 'Downloading data from %s ...' % url
        if resume and os.path.exists(temp_full_name):
            # Download has been interrupted, we try to resume it.
            data = ftplib.FTP()
            parsed_url = urlparse.urlparse(url)
            b_path = os.path.basename(parsed_url.path)
            g_path = parsed_url.path.replace(b_path, "")
            unquoted_g_path = urllib.unquote(g_path)
            data.connect(parsed_url.hostname, parsed_url.port)
            data.login()
            if len(g_path) > 1:
                data.cwd(unquoted_g_path)
        
            local_file_size = os.path.getsize(temp_full_name)
            # If the file exists, then only download the remainder
            try:
                data.sendcmd("TYPE I")
                data.sendcmd("REST " + str(local_file_size))
                print file_name
                down_cmd = "RETR "+ file_name
                local_file = open(temp_full_name, "ab")
                initial_size = local_file_size
                data.retrbinary(down_cmd, local_file.write)
            except urllib2.HTTPError:
                # There is a problem that may be due to resuming. Switch back
                # to complete download method
                return _fetch_file(url, data_dir, resume=False,
                                   overwrite=False)
        else:
            data = urllib2.urlopen(url)
            local_file = open(temp_full_name, "wb")
            _chunk_read_(data, local_file, report_hook=True,
                         initial_size=initial_size, verbose=verbose)
        # temp file must be closed prior to the move
        if not local_file.closed:
            local_file.close()
        shutil.move(temp_full_name, full_name)
        dt = time.time() - t0
        print '...done. (%i seconds, %i min)' % (dt, dt / 60)
    except urllib2.HTTPError, e:
        print 'Error while fetching file %s.' \
            ' Dataset fetching aborted.' % file_name
        if verbose > 0:
            print "HTTP Error:", e, url
        raise
    except urllib2.URLError, e:
        print 'Error while fetching file %s.' \
            ' Dataset fetching aborted.' % file_name
        if verbose > 0:
            print "URL Error:", e, url
        raise
    finally:
        if local_file is not None:
            if not local_file.closed:
                local_file.close()
    if md5sum is not None:
        if (_md5_sum_file(full_name) != md5sum):
            raise ValueError("File %s checksum verification has failed."
                             " Dataset fetching aborted." % local_file)
    return full_name


def _download_status(url, file_name, print_destination=True):
    """Download a URL to a file destination, with status updates"""
    try:
        u = urllib2.urlopen(url)
    except Exception as exc:
        print 'Could not load URL: %s' % url
        raise exc
    with open(file_name, 'wb') as f:
        meta = u.info()
        file_size = int(meta.getheaders("Content-Length")[0])
        stdout.write('Downloading: %s (%s)\n' % (url, sizeof_fmt(file_size)))

        progress = ProgressBar(0, file_size, max_chars=40, spinner=True,
                               mesg='downloading')
        file_size_dl = 0
        block_sz = 65536
        while True:
            buf = u.read(block_sz)
            if not buf:
                break
            file_size_dl += len(buf)
            f.write(buf)
            progress.update(file_size_dl)
        if print_destination is True:
            stdout.write('File saved as %s.\n' % file_name)


def sizeof_fmt(num):
    """Turn number of bytes into human-readable str"""
    unit_list = zip(['bytes', 'kB', 'MB', 'GB', 'TB', 'PB'],
                    [0, 0, 1, 2, 2, 2])
    """Human friendly file size"""
    if num > 1:
        exponent = min(int(log(num, 1024)), len(unit_list) - 1)
        quotient = float(num) / 1024 ** exponent
        unit, num_decimals = unit_list[exponent]
        format_string = '{:.%sf} {}' % (num_decimals)
        return format_string.format(quotient, unit)
    if num == 0:
        return '0 bytes'
    if num == 1:
        return '1 byte'


def _url_to_local_path(url, path):
    """Mirror a url path in a local destination (keeping folder structure)"""
    destination = urlparse.urlparse(url).path
    # First char should be '/', and it needs to be discarded
    if len(destination) < 2 or destination[0] != '/':
        raise ValueError('Invalid URL')
    destination = os.path.join(path, urllib2.url2pathname(destination)[1:])
    return destination


def _check_fname(fname, overwrite):
    """Helper to check for file existence"""
    if not isinstance(fname, basestring):
        raise TypeError('file name is not a string')
    if op.isfile(fname):
        if not overwrite:
            raise IOError('Destination file exists. Please use option '
                          '"overwrite=True" to force overwriting.')
        else:
            logger.info('Overwriting existing file.')


def _check_subject(class_subject, input_subject, raise_error=True):
    """Helper to get subject name from class"""
    if input_subject is not None:
        if not isinstance(input_subject, basestring):
            raise ValueError('subject input must be a string')
        else:
            return input_subject
    elif class_subject is not None:
        if not isinstance(class_subject, basestring):
            raise ValueError('Neither subject input nor class subject '
                             'attribute was a string')
        else:
            return class_subject
    else:
        if raise_error is True:
            raise ValueError('Neither subject input nor class subject '
                             'attribute was a string')
        return None


def _check_pandas_installed():
    try:
        import pandas as pd
        return pd
    except ImportError:
        raise RuntimeError('For this method to work the Pandas library is'
                           ' required.')


def _check_pandas_index_arguments(index, defaults):
    """ Helper function to check pandas index arguments """
    if not any(isinstance(index, k) for k in (list, tuple)):
        index = [index]
    invalid_choices = [e for e in index if not e in defaults]
    if invalid_choices:
        options = [', '.join(e) for e in [invalid_choices, defaults]]
        raise ValueError('[%s] is not an valid option. Valid index'
                         'values are \'None\' or %s' % tuple(options))
