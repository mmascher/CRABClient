import re
import pickle
import os
import time

from CRABClient.Commands.SubCommand import SubCommand
from CRABClient.client_utilities import colors
from CRABClient.client_exceptions import MissingOptionException,ConfigurationException

class remake(SubCommand):
    """
      remake the .requestcache
    """
    name ='remake'
    shortnames = ['rmk']

    def __call__(self):

        #checking regular expression
        tasks = ''.join(self.options.cmptask.split())
        tasks = tasks.split(',')
        remakedtask = []
        self.rejectedtask = []
        self.accpetedtask = []
        for task in tasks:
            if re.match('^\d{6}_\d{6}_([^\:\,]+)\:[a-zA-Z]+_crab_.+' ,task):
                self.accpetedtask.append(task)
            else:
                self.rejectedtask.append(task)
                self.logger.info('%sWarning%s: %s rejected because it does not meet regular expression' % (colors.RED,colors.NORMAL, task))

        if len(self.accpetedtask) < 1:
            raise ConfigurationException("%sError%s: No task name does match regular expression, please use the complete task name from glidemon or dashboard " % (colors.RED,colors.NORMAL))
        else:
            for task in self.accpetedtask:
                result = self.remakecache(task)
                if result != None:
                    remakedtask.append({task : result})
        if len(self.rejectedtask) == 0:
            status = 'SUCCESS'
        elif len(self.accpetedtask) == 0 or len(remakedtask) == 0:
            status = 'FAILED'
        else:
            status = 'PARTIAL SUCCESS'

        if hasattr(self, 'fromapi') and self.fromapi : return {'status' : status , 'result' : {'remaked': remakedtask , 'rejected' : self.rejectedtask}}

    def remakecache(self,taskname):
        #checking and making the request area if does not exist

        username = taskname.split("_")[2].split(":")[-1]
        requestare = taskname.split(username+'_')[1]

        cachepath = os.path.join(requestare , '.requestcache')

        if os.path.exists(cachepath):
            self.logger.info("%sError%s: %s is not created because it is still exist " % (colors.RED,colors.NORMAL,cachepath))
            self.rejectedtask.append(taskname)
        elif not os.path.exists(requestare):
            self.logger.info('Remaking %s folder' %requestare)
            try:
                os.mkdir(requestare)
                os.mkdir(os.path.join(requestare, 'results'))
                os.mkdir(os.path.join(requestare, 'inputs'))
            except IOError:
                self.logger.info('%sWarning%s: Failed to make a requestare' % (colors.RED, colors.NORMAL))
                requestare = os.getcwd()

            self.logger.info('Remaking the .requestcache for %s' % taskname)
            json ={'voGroup': '', 'Server': self.serverurl , 'instance': self.instance,'RequestName': taskname, 'voRole': '', 'Port': ''}
            pickle.dump(json, open(cachepath , 'w'))
            self.logger.info('%sSuccess%s: Finish making %s ' % (colors.GREEN, colors.NORMAL, cachepath))
            return  json

    def setOptions(self):
        """
        __setOptions__

        This allows to set specific command options
        """
        self.parser.add_option( '--cmptask',
                                dest = 'cmptask',
                                default = None,
                                help = 'The complete task name from glidemon or dashboard, use coma to seperate between task')

    def validateOptions(self):

        if not hasattr(self.options, 'cmptask') or  self.options.cmptask == None :
            raise MissingOptionException("%sError%s: Please use the --cmptask option to specify the complete task name "% (colors.RED,colors.NORMAL))


