#!/usr/bin/env python
# encoding: utf-8
"""
This contains some utility methods for the client
"""

import os
import re
import datetime
import logging
import logging.handlers
import commands, string
import time
import pkgutil
import sys
import cPickle
import logging

from string import upper
from optparse import OptionValueError

from CRABClient.client_exceptions import TaskNotFoundException, CachefileNotFoundException, ConfigurationException, ConfigException, HyperNewsNameException

from WMCore.Services.UserFileCache.UserFileCache import UserFileCache
import CRABClient.Emulator

BASEURL = '/crabserver/'
SERVICE_INSTANCES = {'prod': 'cmsweb.cern.ch',
                     'preprod': 'cmsweb-testbed.cern.ch',
                     'dev': 'cmsweb-dev.cern.ch'}

class colors:

    colordict = {
                'RED':'\033[91m',
                'GREEN':'\033[92m',
                'BLUE':'\033[93m',
                'GRAY':'\033[90m',
                'NORMAL':'\033[0m',
                'BOLD':'\033[1m' }

    RED    = colordict['RED']
    GREEN  = colordict['GREEN']
    BLUE   = colordict['BLUE']
    GRAY   = colordict['GRAY']
    NORMAL = colordict['NORMAL']
    BOLD   = colordict['BOLD']


class logfilter(logging.Filter):

    def filter(self, record):
        def removecolor(text):

            for color in colors.colordict.keys():
                if colors.colordict[color] in text:
                    text = text.replace(colors.colordict[color],'')

            return text

        # find color in record.msg

        if isinstance(record.msg, Exception):
            record.msg = removecolor(str(record.msg))
        else:
            record.msg = removecolor(record.msg)
        return True


def getLoggers(loglevel):
    '''
    Logging is using the hierarchy system, the CRAB3.all log inherit everything from CRAB3. So everything that is
    logged to CRAB3.all will also go to CRAB3, however thing that logged using CRAB3 will not go to CRAB3.all.
    CRAB3 logger usess memory handler, which then will be flushed to a filehandler in the 'finally' stage. So

    CRAB3.all -> screen + file
    CRAB3     -> file
    '''

    # Set up the logger and exception handling
    logger = logging.getLogger('CRAB3.all')
    tblogger = logging.getLogger('CRAB3')
    logger.setLevel(logging.DEBUG)

    # Set up console output to stdout at appropriate level
    console_format = '%(message)s'
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(logging.Formatter(console_format))
    console.setLevel(loglevel)
    logger.addHandler(console)

    #setting up a temporary memory logging, the flush level is set to 60, the highest logging level is 50 (.CRITICAL)
    #so any reasonable logging level should not cause any sudden flush
    memhandler = logging.handlers.MemoryHandler(capacity = 1024*10, flushLevel= 60)
    ff = logging.Formatter("%(levelname)s %(asctime)s: \t %(message)s")
    memhandler.setFormatter(ff)
    memhandler.setLevel(logging.DEBUG)
    #adding filter that filter color code
    filter_ = logfilter()
    memhandler.addFilter(filter_)
    tblogger.addHandler(memhandler)

    logger.logfile = os.path.join(os.getcwd(), 'crab.log')

    return logger, memhandler


def getUrl(instance='prod', resource='workflow'):
        """
        Retrieve the url depending on the resource we are accessing and the instance.
        """
        if instance in SERVICE_INSTANCES.keys():
            return BASEURL + instance + '/' + resource
        elif instance == 'private':
            return BASEURL + 'dev' + '/' + resource
        raise ConfigurationException('Error: only %s instances can be used.' %str(SERVICE_INSTANCES.keys()))

def uploadlogfile(logger , proxyfilename , logfilename = None , logpath = None , instance = 'prod' , serverurl = None):

    doupload = True

    if logfilename == None:
        logfilename = str(time.strftime("%Y-%m-%d_%H%M%S"))+'_crab.log'


    if logpath != None:
        if os.path.exists(logpath): pass
        else:
            doupload = False
            logger.debug('%sError%s: %s does not exist' %(colors.RED, colors.NORMAL, logpath))
    else:
        if os.path.exists(str(os.getcwd()) + '/crab.log'):
            logpath = str(os.getcwd())+'/crab.log'
        else:
            logger.debug('%sError%s: Failed to find /crab.log in current director, %s' % (colors.RED, colors.NORMAL, str(os.getcwd())))

    if serverurl == None and instance in SERVICE_INSTANCES.keys():
        serverurl = SERVICE_INSTANCES[instance]
    elif not instance in SERVICE_INSTANCES.keys() and serverurl != None:
        instance = 'private'
    elif not instance in SERVICE_INSTANCES.keys() and serverurl == None:
        logger.debug('%sError%s: serverurl is not None' %(colors.RED, colors.NORMAL, logpath))
        doupload = False

    if proxyfilename == None:
        logger.debug('No proxy is give')
        doupload = False

    baseurl = getUrl(instance = instance , resource = 'info')
    if doupload:
        cacheurl=server_info('backendurls', serverurl, proxyfilename, baseurl)
        cacheurl=cacheurl['cacheSSL']
        cacheurldict={'endpoint' : cacheurl}

        ufc=UserFileCache(cacheurldict)
        logger.debug("cacheURL: %s\nLog file name: %s" % (cacheurl, logfilename))
        logger.info("Uploading log file")
        ufc.uploadLog(logpath, logfilename)

        logfileurl = cacheurl + '/logfile?name='+str(logfilename)
        logger.info("Log file url: %s" %logfileurl)
        return  logfileurl
    else:
        logger.info('Failed to upload the log file')
        logfileurl = False

    return  logfileurl

def getPlugins(namespace, plugins, skip):
    """
    _getPlugins_

    returns a dictionary with key='class name' and value='hook to the module'
    as input needs the package name that contains the different modules

    TODO: If we use WMCore more, replace with the WMFactory.
    """
    packagemod = __import__('%s.%s' % (namespace, plugins), globals(), locals(), plugins)
    fullpath   = packagemod.__path__[0]
    modules = {}
    ## iterating on the modules contained in that package
    for el in list(pkgutil.iter_modules([fullpath])):
        if el[1] not in skip:
            ## import the package module
            mod = __import__('%s.%s.%s' % (namespace, plugins, el[1]), globals(), locals(), el[1])
            ## add to the module dictionary.
            ## N.B. Utilitiy modules like LumiMask do not have classes inside them
            modules[el[1]] = getattr(mod, el[1], None)
            #set the default name if it has not been overridden in the class
            if not hasattr(modules[el[1]], 'name') and modules[el[1]]:
                setattr(modules[el[1]], 'name', modules[el[1]].__name__)

    return modules


def addPlugin(pluginpathname, pluginname = None):
    """
    _addPlugin_

    allows to import an external plug-in and return the dictionary here below
    {
     'plug-name': 'plug-module'
    }

    TODO: add the ability to import a specific module of the file
    """
    modules = {}
    ## file really exists?
    if os.path.exists(pluginpathname):

        ## is that really a file?
        if os.path.isfile(pluginpathname):

            ## get the file name
            pluginfilename = os.path.basename(pluginpathname)

            ## get the directory name and import it if not already
            pluginpath = os.path.dirname(pluginpathname)
            if pluginpath not in sys.path:
                sys.path.append(pluginpath)

            ## get the module name
            mod = os.path.splitext(pluginfilename)[0]

            ## import the module
            imod = __import__(mod)

            ## get the plug-in class
            ## Note: this currently need the module name = plug-in/class name
            modules[mod] = getattr(imod, mod)

    return modules


def getJobTypes(jobtypepath = 'CRABClient', jobtypename = 'JobType'):
    """
    _getJobTypes_

    wrap the dynamic plug-in import for the available job types

    TODO: this can also be a call to get a specific job type from the server
    """
    allplugins = getPlugins(jobtypepath, jobtypename, ['BasicJobType'])
    result = {}
    for k in allplugins:
        result[upper(k)] = allplugins[k]
    return result


def getAvailCommands(subcmdpath = 'CRABClient', subcmdname = 'Commands'):
    """
    _getAvailCommands_

    wrap the dynamic plug-in import for the available commands
    """
    subcmdplugins = getPlugins(subcmdpath, subcmdname, ['SubCommand'])
    result = {}
    for k in subcmdplugins.keys():
        if subcmdplugins[k].visible:
            result[k] = subcmdplugins[k]

    return result


def getRequestName(requestName = None):
    """
    _getRequestName_

    create the directory name
    """
    prefix  = 'crab_'
    postfix = str(datetime.datetime.now().strftime("%Y%m%d_%H%M%S"))

    if requestName is None or not isinstance(requestName,str) or len(requestName) == 0:
        return prefix + postfix
    elif '/' in requestName:
        msg = '%sError %s: The "/" character is not accepted in the requestName parameter.\
         If your intention was to specity the location of your task, please use the config.General.workArea parameter' \
              % (colors.RED, colors.NORMAL)
        raise ConfigurationException(msg)
    else:
        return prefix + requestName # + '_' + postfix


def changeFileLogger(logger, workingpath = os.getcwd(), logname = 'crab.log'):
    """
    change file logger destination
    """
    logfullpath = os.path.join( workingpath, logname )
    logging.getLogger('CRAB3.all').logfile = logfullpath

    return logfullpath


def createWorkArea(logger, workingArea = '.', requestName = ''):
    """
    _createWorkArea_

    creates the working directory with the needed sub-folders
    in case it already exists it raises an exception
    """

    if workingArea is None or workingArea == '.' :
        workingArea = os.getenv('CRAB_WORKING_AREA', '.')
    elif not os.path.isabs(workingArea):
        workingArea = os.path.abspath(workingArea)

    ## create the working area if it is not there
    if not os.path.exists(workingArea):
        os.makedirs(workingArea)

    requestName = getRequestName(requestName)

    fullpath = os.path.join(workingArea, requestName)

    ## checking if there is no a duplicate
    if os.path.exists(fullpath):
        raise ConfigException("Working area '%s' already exists \nPlease change the requestName in the config file" % fullpath)

    ## creating the work area
    os.mkdir(fullpath)
    os.mkdir(os.path.join(fullpath, 'results'))
    os.mkdir(os.path.join(fullpath, 'inputs'))

    ## define the log file
    logfile = changeFileLogger( logger, workingpath = fullpath )

    return fullpath, requestName, logfile


def createCache(requestarea, host, port, uniquerequestname, voRole, voGroup, instance, originalConfig={}):
    touchfile = open(os.path.join(requestarea, '.requestcache'), 'w')
    neededhandlers = {
                      "Server" : host,
                      "Port" : port,
                      "RequestName" : uniquerequestname,
                      "voRole" : voRole,
                      "voGroup" : voGroup,
                      "instance" : instance,
                      "OriginalConfig" : originalConfig
                     }
    cPickle.dump(neededhandlers, touchfile)
    touchfile.close()


def getWorkArea( task ):
    requestarea = ''
    requestname = ''
    if os.path.isabs( task ):
        requestarea = task
        requestname = os.path.split(os.path.normpath(requestarea))[1]
    else:
        requestarea = os.path.abspath( task )
        requestname = task
    return requestarea, requestname


def loadCache( task, logger ):
    requestarea, requestname = getWorkArea( task )
    cachename = os.path.join(requestarea, '.requestcache')
    taskName = task.split('/')[-1] #Contains only the taskname without the path

    #Check if the task directory exists
    if not os.path.isdir( requestarea ):
        msg = 'Working directory for task %s not found ' % taskName
        raise TaskNotFoundException( msg )
    #If the .requestcache file exists open it!
    if os.path.isfile(cachename):
        loadfile = open( cachename, 'r' )
    else:
        msg = 'Cannot find .requestcache file inside the working directory for task %s' % taskName
        raise CachefileNotFoundException( msg )

    logfile = changeFileLogger( logger, workingpath = requestarea )
    return cPickle.load(loadfile), logfile


def getUserName(voRole, voGroup, logger):
    _, _, proxy = initProxy(voRole, voGroup, logger)
    return proxy.getUserName()


def getHyperNewsName():
    ## Direct stderr from voms-proxy-* to dev/null to avoid stupid Java messages :-(
    status, proxy_file_name = commands.getstatusoutput('eval `scram unsetenv -sh`; voms-proxy-info -path 2>/dev/null')
    status, proxy_time_left = commands.getstatusoutput('eval `scram unsetenv -sh`; voms-proxy-info -timeleft 2>/dev/null')
    capath = os.environ['X509_CERT_DIR'] if 'X509_CERT_DIR' in os.environ else '/etc/grid-security/certificates'
    cmd  = "curl -s --capath %s --cert %s --key %s 'https://cmsweb.cern.ch/sitedb/data/prod/whoami'" % (capath, proxy_file_name, proxy_file_name)
    cmd += " | tr ':,' '\n'"
    cmd += " | grep -A1 login"
    cmd += " | tail -1"
    status, hn_username = commands.getstatusoutput(cmd)
    hn_username = string.strip(hn_username).replace('"','')
    if not hn_username:
        raise HyperNewsNameException("Unable to retrieve CMS HyperNews username from SiteDB")
    return hn_username


def validServerURL(option, opt_str, value, parser):
    """
    This raises an optparse error if the url is not valid
    """
    if value is not None:
        if not validURL(value):
            raise OptionValueError("%s option value '%s' not valid." % (opt_str, value))
        setattr(parser.values, option.dest, value)
    else:
        setattr(parser.values, option.dest, option.default)


def validURL(serverurl, attrtohave = ['scheme', 'netloc', 'hostname'], attrtonothave = ['path', 'params', 'query', 'fragment', 'username', 'password']):
    """
    returning false if the format is different from https://host:port
    """
    tempurl = serverurl
    if not serverurl.startswith('https://'):
        tempurl = 'https://' + serverurl
    from urlparse import urlparse
    parsedurl = urlparse(tempurl)
    for elem in attrtohave:
        elemval = getattr(parsedurl, elem, None)
        if str( elemval ) == '' or elemval is None:
            return False
    for elem in attrtonothave:
        elemval = getattr(parsedurl, elem, None)
        if not str( elemval ) == '' and elemval is not None:
            return False
    return True


def validateJobids(jobids):
    #check the format of jobids
    if re.match('^\d+((?!(-\d+-))(\,|\-)\d+)*$',jobids):
        jobid=[]
        element=jobids.split(',')
        for number in element:
            if '-' in number:
                sub=number.split('-')
                jobid.extend(range(int(sub[0]),int(sub[1])+1))
            else:
                jobid.append(int(number))
        #removing duplicate and sort the list
        jobid = list(set(jobid))
        return [('jobids',job) for job in jobid]
    else:
        raise ConfigurationException("The command line option jobids should be a comma separated list of integers or range, no whitespace")


#XXX Trying to do it as a Command causes a lot of headaches (and workaround code).
#Since server_info class needs SubCommand, and SubCommand needs server_info for
#delegating the proxy then we are screwed
#If anyone has a better solution please go on, otherwise live with that one :) :)
from CRABClient.client_exceptions import RESTCommunicationException
from CRABClient import __version__

def server_info(subresource, server, proxyfilename, baseurl, **kwargs):
    """
    Get relevant information about the server
    """
    server = CRABClient.Emulator.getEmulator('rest')(server, proxyfilename, proxyfilename, version=__version__)
    requestdict= {'subresource' : subresource}
    requestdict.update(**kwargs)
    dictresult, status, reason = server.get(baseurl, requestdict)

    return dictresult['result'][0]
