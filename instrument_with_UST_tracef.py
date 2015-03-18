#!/usr/bin/env python3
import os, re, fileinput, json, shutil as shu
from functools import reduce

"""
should be looking for
SaAmfCallbacksT    reg_callback_set = {
  .saAmfCSISetCallback = vlc_amf_csi_set_callback,
  .saAmfCSIRemoveCallback = vlc_amf_csi_remove_callback,
  .saAmfComponentTerminateCallback = vlc_amf_comp_terminate_callback,
}
(?<=preceding_pattern=)(.+)(?=tailing_pattern)
(?<=Value=)(?P<value>.*?)(?=&)
"""
def colorString(string, *stringAttrs, **allStringAttrs):
    colorMap = {\
        'PURPLE' : '\033[95m',\
        'CYAN' : '\033[96m',\
        'DARKCYAN' : '\033[36m',\
        'BLUE' : '\033[94m',\
        'GREEN' : '\033[92m',\
        'YELLOW' : '\033[93m',\
        'RED' : '\033[91m',\
        'BOLD' : '\033[1m',\
        'UNDERLINE' : '\033[4m',\
        'END' : '\033[0m'}
    if len(stringAttrs)>0:
        for attr in stringAttrs:
            string = colorMap.get(str(attr).upper()) + str(string) + colorMap['END']
    if len(allStringAttrs)>0:
        for stringAttrTuple in allStringAttrs.values():
            for attr in stringAttrTuple:
                string = colorMap.get(str(attr).upper()) + str(string) + colorMap['END']
    return string

def flatTuples(path):
    retlist=[]    
    for dirpaths, dirs, files in os.walk(path):
        for aFile in files:
            retlist.append(dirpaths+os.sep+aFile)
    retlist.remove(os.getcwd()+'/instrument_with_UST_tracef.py')
    if os.path.isfile('./funcMap.json'): retlist.remove(os.getcwd()+'/funcMap.json')
    return retlist
 
def matchAndReturn(aFile, strings):
    matchedLines = []
    with open(aFile, 'r', encoding="latin-1") as oneFile:
        for num, line in enumerate(oneFile, 1):
            for string in strings:
                if string in line:
                    matchedLines.append([num, line])
    return matchedLines

#Class for updating the compilation link to liblttng-ust
class linker(object):
    """instrumentation linker-handler"""
    def __init__(self, signature, stringAddition):
        self.__linkerFiles = []
        self.__signature = signature
        self.__replacement = signature + ' ' + stringAddition

    def getLinkerFiles(self):
        for aFile in flatTuples(os.getcwd()): 
            matchedLines = matchAndReturn(aFile, [self.__signature])
            if matchedLines!=None and len(matchedLines)!=0:
                for aLine in matchedLines:
                    ##Color-printing the results
                    #print("\n"+colorString(aLine[1], 'red')+ " found at line " + colorString(str(aLine[0]),'cyan') + " in file " + colorString(aFile,'bold'))
                    self.__linkerFiles.append([aFile,aLine[0],aLine[1]])
        return self.__linkerFiles

    def update(self):
        writerString =""
        if not os.path.exists('../linker_backup'): os.makedirs('../linker_backup')
        if len(self.__linkerFiles)==0: self.getLinkerFiles()
        for oneEntry in self.__linkerFiles:
            shu.copyfile(oneEntry[0] , '../linker_backup/'+oneEntry[0].rsplit('/',1)[1])
            with open(oneEntry[0],'r') as oneFile:
                writerString = oneFile.read()
            with open(oneEntry[0], 'w') as oneFile:
                oneFile.write(re.sub(self.__signature, self.__replacement, writerString, re.M))
            print("Successfully updated linkers in config-file : '%s'" %(oneEntry[0]))


#Class for updating the dispatch-functions
class dispatchCalls(object):
    def __init__(self):
        self.__funcFiles = []
        self.__funcMap = {'csiSetFunction':{'funcName':None, 'functionDeclarations':[]}\
                        , 'csiRemoveFunction':{'funcName':None, 'functionDeclarations':[]}\
                        , 'saAmfComponentTerminateCallback':{'funcName':None, 'functionDeclarations':[]}}

    def instrument(self):
        regex_componentNameExtracter = re.compile(r'(?<=SaNameT)(.*?)(?=\)|,)', re.DOTALL)
        regex_csiNameExtracter = re.compile(r'(?<=SaAmfCSIDescriptorT)(.*?)(?=\)|,)', re.DOTALL)
        regex_haStateExtracter = re.compile(r'(?<=SaAmfHAStateT)(.*?)(?=\)|,)', re.DOTALL)
        regex_csiFlags = re.compile(r'(?<=SaAmfCSIFlagsT)(.*?)(?=\)|,)', re.DOTALL)
        allFilesDirs = flatTuples(os.getcwd())
        fileString = ""
        for aFile in allFilesDirs: self.mapCSIsetFunctions(aFile)
        for fkey in self.__funcMap:
            if self.__funcMap[fkey]['funcName']!=None: self.__funcMap[fkey]['funcRegex'] = self.__funcMap[fkey]['funcName']+r'\([^)]*\)\s*\n*\s*\{'
        for aFile in allFilesDirs:
            with open(aFile,'r',encoding="latin-1") as ff: fileString = ff.read()
            for fkey in self.__funcMap:
                self.__funcMap[fkey]['functionDeclarations'] += re.findall(self.__funcMap[fkey]['funcRegex'], fileString, re.DOTALL)            
            if len(self.__funcMap['csiSetFunction']['functionDeclarations'])>0:
                for aFunctionDeclaration in self.__funcMap['csiSetFunction']['functionDeclarations']:
                    compName = regex_componentNameExtracter.search(aFunctionDeclaration).group(0).replace(" ","").strip("*") if regex_componentNameExtracter.search(aFunctionDeclaration) else ""
                    csiName = regex_csiNameExtracter.search(aFunctionDeclaration).group(0).replace(" ","") if regex_csiNameExtracter.search(aFunctionDeclaration)!=None else ""
                    haState = regex_haStateExtracter.search(aFunctionDeclaration).group(0).replace(" ","") if regex_haStateExtracter.search(aFunctionDeclaration)!=None else ""
                    #For HA-state, it is assumed you use string instead of numbers. The enum for HA-state string is assumed to be 'ha_state_str' here. Change it in the line below if it is otherwise
                    instrumentedString = aFunctionDeclaration+"\n\
                    //////////Auto-Instrumented code starts//////////\n\
                    int component_module_pid = getpid();\n\
                    tracef(\"{'type':'dispatch_set', 'CSI':'%s', 'component':'%s' , 'HAState':'%s', 'PID':%d},\""+csiName+".csiName.value, "+compName+"->value ,ha_state_str["+haState+"], component_module_pid);\n\
                    //////////Auto-Instrumented code ends//////////\n\n"
                    fileString = re.sub(self.__funcMap['csiSetFunction']['funcRegex'], instrumentedString, fileString)
                with open(aFile,'w') as fileToInstrument: fileToInstrument.write(fileString)
                print("Instrumented file: '%s' for function '%s'" %(aFile, self.__funcMap['csiSetFunction']['funcName']))
                self.__funcMap['csiSetFunction']['functionDeclarations'] = []            
            if len(self.__funcMap['csiRemoveFunction']['functionDeclarations'])>0:
                for aFunctionDeclaration in self.__funcMap['csiRemoveFunction']['functionDeclarations']:
                    compName = regex_componentNameExtracter.search(aFunctionDeclaration).group(0).replace(" ","").strip("*") if regex_componentNameExtracter.search(aFunctionDeclaration) else ""
                    csiName = re.findall(r'(?<=const SaNameT)(.*?)(?=\)|,)', aFunctionDeclaration)[1].replace(" ","").strip("*") if len(re.findall(r'(?<=const SaNameT)(.*?)(?=\)|,)', aFunctionDeclaration))>1 else ""
                    instrumentedString = aFunctionDeclaration+"\n\
                    //////////Auto-Instrumented code starts//////////\n\
                    int component_module_pid = getpid();\n\
                    tracef(\"{'type':'dispatch_remove' , 'component': '%s' , 'CSI':'%s', 'PID': '%d'}\","+compName+"->value, "+csiName+"->value, component_module_pid);\n\
                    //////////Auto-Instrumented code ends//////////\n\n"
                    fileString = re.sub(self.__funcMap['csiRemoveFunction']['funcRegex'], instrumentedString, fileString)
                    #print(instrumentedString)
                with open(aFile,'w') as fileToInstrument: fileToInstrument.write(fileString)
                print("Instrumented file: '%s' for function '%s'" %(aFile, self.__funcMap['csiRemoveFunction']['funcName']))
                self.__funcMap['csiRemoveFunction']['functionDeclarations'] = []
            if len(self.__funcMap['saAmfComponentTerminateCallback']['functionDeclarations'])>0:
                for aFunctionDeclaration in self.__funcMap['saAmfComponentTerminateCallback']['functionDeclarations']:
                    compName = regex_componentNameExtracter.search(aFunctionDeclaration).group(0).replace(" ","").strip("*") if regex_componentNameExtracter.search(aFunctionDeclaration) else ""
                    instrumentedString = aFunctionDeclaration+"\n\
                    //////////Auto-Instrumented code starts//////////\n\
                    int component_module_pid = getpid();\n\
                    tracef(\"{ 'type':'dispatch_terminate' ,'component': '%s', 'PID': '%d'}\", "+compName+"->value, component_module_pid);\n\
                    //////////Auto-Instrumented code ends//////////\n\n"
                    fileString = re.sub(self.__funcMap['saAmfComponentTerminateCallback']['funcRegex'], instrumentedString, fileString)
                    #print(instrumentedString)
                with open(aFile,'w') as fileToInstrument: fileToInstrument.write(fileString)
                print("Instrumented file: '%s' for function '%s'" %(aFile, self.__funcMap['saAmfComponentTerminateCallback']['funcName']))
                self.__funcMap['saAmfComponentTerminateCallback']['functionDeclarations'] = []
        return self.__funcMap


    def mapCSIsetFunctions(self, aFile):
        regex_csiSetMatcher = re.compile("(?<=saAmfCSISetCallback=)(?P<value>.*?)(?=\W+)", re.DOTALL)
        regex_csiRemoveMatcher = re.compile("(?<=saAmfCSIRemoveCallback=)(?P<value>.*?)(?=\W+)", re.DOTALL)
        regex_componentTerminateMatcher = re.compile("(?<=saAmfComponentTerminateCallback=)(?P<value>.*?)(?=\W+)", re.DOTALL)
        trimmedLine = ""
        with open(aFile,'r',encoding="latin-1") as oneFile: trimmedLine = "".join(oneFile.read().split())         
        if regex_csiSetMatcher.search(trimmedLine)!=None: 
            self.__funcMap['csiSetFunction']['funcName'] = regex_csiSetMatcher.search(trimmedLine).group('value')
        if regex_csiRemoveMatcher.search(trimmedLine)!=None:
            self.__funcMap['csiRemoveFunction']['funcName'] = regex_csiRemoveMatcher.search(trimmedLine).group('value')
        if regex_componentTerminateMatcher.search(trimmedLine)!=None: 
            self.__funcMap['saAmfComponentTerminateCallback']['funcName'] = regex_componentTerminateMatcher.search(trimmedLine).group('value')
        return self.__funcMap


if __name__ == '__main__':
    #print(dispatchCalls().instrument())
    print(colorString("Instrumenting dispatch-calls",'yellow','bold'))
    dispatchCalls().instrument()
    print(colorString("Instrumenting configuration files for linkers",'yellow','bold'))
    linker("-lSaAmf -lSaCkpt", "-ldl -llttng-ust").update()

