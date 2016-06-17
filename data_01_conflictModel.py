# Copyright:   (c) Oskar Petersons 2013

"""Core data model and class definitions for GMCR-py."""

import json
import data_03_gmcrUtilities as gmcrUtil


class Option:
    def __init__(self,name,masterList,permittedDirection='both'):
        self.name = str(name)
        self.permittedDirection = permittedDirection
        self.refs = 0
    
    def __str__(self):
        return self.name
        
    def addRef(self):
        self.refs += 1
        
    def remRef(self):
        self.refs -= 1
        
    def export_rep(self):
        return {'name':str(self.name),
                'permittedDirection':str(self.permittedDirection)}
        
class DecisionMaker:
    def __init__(self,conflict,name):
        self.name = str(name)
        self.isCoalition = False
        self.conflict = conflict
        self.options = OptionList(conflict.options)
        self.preferences = ConditionList(conflict)
        self.lastCalculatedPreferences = None

    def __str__(self):
        return self.name
        
    def export_rep(self):
        self.calculatePreferences()
        rep  = {}
        rep['name'] = str(self.name)
        rep['options'] = self.options.export_rep()
        rep['preferences'] = self.preferences.export_rep()
        rep['payoffs'] = self.payoffs.tolist()
        if self.conflict.useManualPreferenceRanking:
            rep['preferenceRanking'] = self.preferenceRanking
        return rep
        
    def full_rep(self):
        return self.export_rep()

    def addOption(self,option):
        if option not in self.options:
            self.options.append(option)
        
    def removeOption(self,option):
        if option in self.options:
            self.options.remove(option)
            
    def onDelete(self):
        print([x.name for x in self.options])
        for opt in reversed(self.options):
            self.removeOption(opt)
        print([x.name for x in self.options])
        for co in self.conflict.coalitions:
            if co is self:
                self.conflict.coalitions.remove(self)
            if isinstance(co,Coalition):
                co.remove(self)
                break
            
    def weightPreferences(self):
        for idx,pref in enumerate(self.preferences):
            pref.weight = 2**(len(self.preferences)-idx-1)
            
    def calculatePreferences(self):
        if self.conflict.useManualPreferenceRanking:
            self.payoffs = gmcrUtil.mapPrefRank2Payoffs(self.preferenceRanking,self.conflict.feasibles)
            self.usedRanking = self.conflict.useManualPreferenceRanking
        elif (self.lastCalculatedPreferences != self.preferences.export_rep() or
              self.usedRanking != self.conflict.useManualPreferenceRanking    or
              self.oldFeasibles != self.conflict.feasibles.decimal):
              
            self.lastCalculatedPreferences   = self.preferences.export_rep()
            self.usedRanking = self.conflict.useManualPreferenceRanking
            self.oldFeasibles = list(self.conflict.feasibles.decimal)
              
            self.preferences.validate()
            self.weightPreferences()
            result = gmcrUtil.prefPriorities2payoffs(self.preferences,self.conflict.feasibles)
            self.payoffs = result[0]
            self.preferenceRanking = result[1]


class Condition:
    """A list of options either taken or not taken against which a state can be tested."""
    def __init__(self,conflict,condition):
        self.conflict = conflict
        self.options = OptionList(conflict.options)
        self.taken = []
        for opt,taken in condition:
            self.options.append(opt)
            self.taken.append(taken)
        self.name = self.ynd()
        self.isCompound = False

    def __str__(self):
        return self.name + " object"
        
    def updateName(self):
        self.name = self.ynd()
        
    def cond(self):
        """The condition represented as tuples of options and whether or not they are taken."""
        return zip(self.options,self.taken)
        
    def ynd(self):
        """Returns the condition in 'Yes No Dash' notation."""
        self.conflict.options.set_indexes()
        ynd = ['-']*len(self.conflict.options)
        for opt,taken in self.cond():
            ynd[opt.master_index] = taken
        return ''.join(ynd)
        
    def test(self,state):
        """Test against a decimal state. Returns True if state satisfies the Condition."""
        self.conflict.options.set_indexes()
        state = gmcrUtil.dec2yn(state,len(self.conflict.options))
        for opt,taken in self.cond():
            if state[opt.master_index] != taken:
                return False
        return True
        
    def isValid(self):
        """Returns false if one of the options the condition depends on has been removed form the conflict."""
        for opt in self.options:
            if opt not in self.conflict.options:
                return False
        self.updateName()
        return True
        
    def export_rep(self):
        self.conflict.options.set_indexes()
        return [(opt.master_index,taken) for opt,taken in self.cond()]

class CompoundCondition:
    """A condition defined as a union of simple conditions."""
    def __init__(self,conflict,conditions):
        self.conflict = conflict
        self.conditions = [Condition(self.conflict,dat) for dat in conditions]
        self.isCompound = True
        self.updateName()
        
    def __str__(self):
        return self.name + " object"
        
    def index(self,i):
        return self.conditions.index(i)
    
    def __len__(self):
        return len(self.conditions)
        
    def __getitem__(self,key):
        return self.conditions[key]
        
    def __iter__(self):
        return iter(self.conditions)
        
    def updateName(self):
        self.name = str(sorted(self.ynd()))[1:-1].replace("'",'')
        
    def append(self,condition):
        """Adds the condition given to the compound condition."""
        self.conditions.append(condition)
        self.updateName()
        
    def __delitem__(self,key):
        """Removes the condition at idx from the compound condition."""
        del self.conditions[key]
        self.updateName()
    
    def ynd(self):
        """Returns the compound condition as a list with items in 'Yes No Dash' notation."""
        return [cond.ynd() for cond in self.conditions]
        
        
    def test(self,state):
        """Test against a decimal state. Returns True if state satisfies one or
        more of the component conditions."""
        for cond in self.conditions:
            if cond.test(state):
                return True
        return False

    def isValid(self):
        """Returns False if one of the options the condition depends on has been removed from the conflict."""
        for cond in self.conditions:
            if not cond.isValid():
                return False
        self.updateName()
        return True
    
    def export_rep(self):
        return {"compound":True,"members":[cond.export_rep() for cond in self.conditions]}
    

class ObjectList:
    def __init__(self,masterList=None):
        self.itemList = []
        self.masterList = masterList
                
    def __len__(self):
        return len(self.itemList)
        
    def __getitem__(self,key):
        return self.itemList[key]
        
    def __setitem__(self,key,value):
        self.itemList[key] = value
        
    def __delitem__(self,key):
        item = self.itemList[key]
        del self.itemList[key]
        if self.masterList is not None:
            self.masterList.remove(item)
        
    def remove(self,item):
        self.itemList.remove(item)
        if self.masterList is not None:
            self.masterList.remove(item)
        
    def __iter__(self):
        return iter(self.itemList)
        
    def __reversed__(self):
        return reversed(self.itemList)
        
    def __contains__(self,item):
        return item in self.itemList
        
    def insert(self,i,x):
        self.itemList.insert(i,x)
        
    def pop(self,i=None):
        return self.itemList.pop(i)
        
    def index(self,i):
        return self.itemList.index(i)
        
    def set_indexes(self):
        for idx,item in enumerate(self.itemList):
            item.master_index = idx
            item.dec_val = 2**(idx)
            
    def names(self):
        return [item.name for item in self.itemList]

            
class DecisionMakerList(ObjectList):
    def __init__(self,conflict):
        ObjectList.__init__(self)
        self.conflict = conflict
        
    def __str__(self):
        return str([dm.name for dm in self])

    def export_rep(self):
        return [x.export_rep() for x in self.itemList]

    def append(self,item):
        if isinstance(item,DecisionMaker) and item not in self.itemList:
            self.itemList.append(item)
        elif isinstance(item,str):
            self.itemList.append(DecisionMaker(self.conflict,item))
            
    def __delitem__(self,key):
        self.itemList[key].onDelete()
        del self.itemList[key]

    def from_json(self,dmData):
        newDM = DecisionMaker(self.conflict,dmData['name'])
        for optIdx in dmData['options']:
            newDM.options.append(self.conflict.options[int(optIdx)])
        for preference in dmData['preferences']:
            newDM.preferences.from_json(preference)
        if self.conflict.useManualPreferenceRanking:
            try:
                newDM.preferenceRanking = dmData['preferenceRanking']
            except KeyError:
                newDM.preferenceRanking = dmData['preferenceVector']        # for compatibility with old save files 
        self.append(newDM)

class OptionList(ObjectList):
    def __init__(self,masterList=None):
        ObjectList.__init__(self,masterList)
        
    def export_rep(self):
        if self.masterList is not None:
            self.masterList.set_indexes()
            return [x.master_index for x in self.itemList]
        else:
            return [x.export_rep() for x in self.itemList]

    def append(self,item):
        if isinstance(item,Option) and item not in self.itemList:
            self.itemList.append(item)
            if self.masterList is not None:
                item.addRef()
                if item not in self.masterList:
                    self.masterList.append(item)
        elif isinstance(item,str):
            if self.masterList is None:
                newOption = Option(item,self)
            else:
                newOption = Option(item,self.masterList)
                self.masterList.append(newOption)
                newOption.addRef()
            self.itemList.append(newOption)

                
                
    def from_json(self,optData):
        newOption = Option(optData['name'],self.masterList,optData['permittedDirection'])
        self.append(newOption)
            
class ConditionList(ObjectList):
    def __init__(self,conflict):
        ObjectList.__init__(self)
        self.conflict = conflict
        
    def export_rep(self):
        return [x.export_rep() for x in self.itemList]
        
    def from_json(self,condData):
        """Replaces the option number with the actual option object."""
        if isinstance(condData,list):
            for opt in condData:
                opt[0] = self.conflict.options[opt[0]]
        elif isinstance(condData,dict):
            for mem in condData['members']:
                for opt in mem:
                    opt[0] = self.conflict.options[opt[0]]
        self.append(condData)

    def append(self,item):
        if isinstance(item,Condition) or isinstance(item,CompoundCondition):
            newCondition = item
        elif isinstance(item,list):
            newCondition = Condition(self.conflict,item)
        elif isinstance(item,dict):
            newCondition = CompoundCondition(self.conflict,item['members'])
        else:
            raise TypeError('Not a valid Condition Object')
            
        if newCondition.name not in [cond.name for cond in self]:
            self.itemList.append(newCondition)
        else:
            print("attempted to add duplicate; ignored")
            
    def moveCondition(self,idx,targ):
        """Move a condition from position idx in the list to position targ."""
        j = self.pop(idx)
        self.insert(targ,j)

    def removeCondition(self,idx):
        """Remove the Condition at position idx"""
        del self[idx]
        
    def validate(self):
        toRemove = []
        for idx,pref in enumerate(self):
            if not pref.isValid():
                toRemove.append(idx)
        for idx in toRemove[::-1]:
            del self[idx]
            
    def format(self,fmt="YN-"):
        """Returns the conditions in the specified format.
        
        Valid formats are:
        'YN-': uses 'Y','N', and '-' to represent infeasible states compactly.
        'YN': lists all infeasible states using 'Y' and 'N'.
        'dec': lists all infeasible states in decimal form.
        """
        if fmt == 'YN-':
            return [x.ynd() for x in self]
        if fmt == 'YN':
            return sorted(set(gmcrUtil.expandPatterns(self.format('YN-'))))
        if fmt == 'dec':
            return [self.yn2dec(state) for state in self.format('YN')]
        else:
            print('invalid format')


class FeasibleList:
    def __init__(self,dash=None):
        if not dash:
            self.decimal = []
            self.dash = []
            return
        self.dash = gmcrUtil.reducePatterns(dash)                               #as 'Y,N,-' compact patterns
        temp = sorted([(gmcrUtil.yn2dec(yn),yn) for yn in gmcrUtil.expandPatterns(self.dash)])
        self.yn = [yn for dec,yn in temp]                                       #as 'Y,N' patterns
        self.decimal   = [dec for dec,yn in temp]                               #as decimal values
        self.toOrdered,self.toDecimal = gmcrUtil.orderedNumbers(self.decimal)   #conversion dictionaries
        self.ordered = sorted(self.toDecimal.keys())                            #as ordered numbers
        self.ordDec = ['%3d  [%s]'%(ord,dec) for ord,dec in zip(self.ordered,self.decimal)]     #special display notation

    def __len__(self):
        return len(self.decimal)

    def __iter__(self):
        return iter(range(len(self.decimal)))

class Coalition:
    """Combination of two or more decision makers. Has interfaces equivalent to DMs."""
    def __init__(self,conflict,dms):
        self.members = dms
        self.isCoalition = True
        self.conflict = conflict
        self.refresh()
        
    def refresh(self):
        self.name = ', '.join([dm.name for dm in self.members])
        self.options = OptionList(self.conflict.options)
        
        for dm in self.members:
            for opt in dm.options:
                self.options.append(opt)
                
        self.preferences = ConditionList(self.conflict)
        self.calculatePreferences()
                
    def __str__(self):
        return self.name
        
    def __iter__(self):
        return iter(self.members)
        
    def __delitem__(self,key):
        del self.members[key]
        self.refresh()
        
    def remove(self,dm):
        if dm in self.members:
            self.members.remove(dm)
            self.refresh()
        
    def __contains__(self,dm):
        return dm in self.members
        
    def insert(self,i,x):
        self.members.insert(i,x)
        self.refresh()
        
    def export_rep(self):
        if len(self.members) > 1:
            return [self.conflict.decisionMakers.index(dm) for dm in self.members]
        else:
            return self.conflict.decisionMakers.index(self.members[0])
        
    def disp_rep(self):
        if len(self.members) > 1:
            return [self.conflict.decisionMakers.index(dm)+1 for dm in self.members]
        else:
            return self.conflict.decisionMakers.index(self.members[0])+1
            
    def full_rep(self):
        rep  = {}
        rep['name'] = str(self.name)
        rep['options'] = self.options.export_rep()
        return rep
            
    def calculatePreferences(self):
        for dm in self.members:
            dm.calculatePreferences()
        self.payoffs = [", ".join([str(dm.payoffs[state]) for dm in self.members]) for state in self.conflict.feasibles]
        
        
        
class CoalitionList(ObjectList):
    def __init__(self,conflict):
        ObjectList.__init__(self)
        self.conflict = conflict

    def export_rep(self):
        working = list(self.itemList)
        for idx,item in enumerate(working):
            if isinstance(item,DecisionMaker):
                working[idx] = self.conflict.decisionMakers.index(item)
            else:
                working[idx] = item.export_rep()
        return working
        
    def full_rep(self):
        return [x.full_rep() for x in self.itemList]
        
    def disp_rep(self):
        working = list(self.itemList)
        for idx,item in enumerate(working):
            if isinstance(item,DecisionMaker):
                working[idx] = self.conflict.decisionMakers.index(item)+1
            else:
                working[idx] = item.disp_rep()
        return working

    def append(self,item):
        if isinstance(item,Coalition) and item not in self.itemList:
            self.itemList.append(item)
        elif isinstance(item,DecisionMaker):
            self.itemList.append(item)
        else:
            raise TypeError("%s is not a Coalition"%item)

    def from_json(self,coData):
        if isinstance(coData,int):
            memberList = [self.conflict.decisionMakers[int(coData)]]
        elif isinstance(coData,list):
            memberList = [self.conflict.decisionMakers[int(dmIdx)] for dmIdx in coData]
        newCO = Coalition(self.conflict,memberList)
        self.append(newCO)
        
    def validate(self):
        dms = list(self.conflict.decisionMakers)
        for co in self.itemList:
            if isinstance(co,Coalition):
                for dm in co:
                        dms.remove(dm)
            else:
                dms.remove(co)
        if len(dms) == 0:
            return True
        return False
        

class ConflictModel:
    def __init__(self):
        """Initializes a new, empty conflict."""

        self.options = OptionList()       #list of Option objects
        self.decisionMakers = DecisionMakerList(self)        #list of DecisonMaker objects
        self.infeasibles  = ConditionList(self)       #list of Condition objects
        self.feasibles = FeasibleList()

        self.useManualPreferenceRanking = False
        self.preferenceErrors = None
        self.coalitions = CoalitionList(self)

        
    def newCondition(self,condData):
        return Condition(self,condData)
        
    def newCompoundCondition(self,condData):
        return CompoundCondition(self,condData)
        
    def newCoalition(self,coalitionData):
        return Coalition(self,coalitionData)

    def export_rep(self):
        """Generates a representation of the conflict suitable for JSON encoding."""
        self.reorderOptionsByDM()
        return {'decisionMakers':self.decisionMakers.export_rep(),
                'coalitions':self.coalitions.export_rep(),
                'coalitionsFull': self.coalitions.full_rep(),
                'options':self.options.export_rep(),
                'infeasibles':self.infeasibles.export_rep(),
                'useManualPreferenceRanking':self.useManualPreferenceRanking,
                'program':'gmcr-py',
                'version':'0.3.12'}
        
    def save_to_file(self,file):
        """Saves the current conflict to the file location given."""
        print(self.export_rep())
        try:
            fileObj = open(file,mode='w')
        except IOError:
            print('file not readable')
            return
        try:
            json.dump(self.export_rep(),fileObj)
        finally:
            fileObj.close()

    def json_import(self,d):
        """Imports values into the conflict from JSON data d"""
        try:
            self.useManualPreferenceRanking = d['useManualPreferenceRanking']
        except KeyError:
            self.useManualPreferenceRanking = d['useManualPreferenceVectors']   # old save file compatibility
        for optData in d['options']:
            self.options.from_json(optData)
        for dmData in d['decisionMakers']:
            self.decisionMakers.from_json(dmData)
        for infData in d['infeasibles']:
            self.infeasibles.from_json(infData)
        self.reorderOptionsByDM()
        self.infeasibles.validate()
        self.recalculateFeasibleStates(True)
        for dm in self.decisionMakers:
            dm.calculatePreferences()
        try:
            for coData in d['coalitions']:
                self.coalitions.from_json(coData)
        except KeyError:
            for dm in self.decisionMakers:
                self.coalitions.append(dm)
        if not self.coalitions.validate():
            print('Coalitions failed to validate, reseting')
            self.coalitions = CoalitionList(self)
            for dm in self.decisionMakers:
                self.coalitions.append(dm)
            if not self.coalitions.validate():
                raise Exception("Coalitions Failure")
            


    def load_from_file(self,file):
        """Load a conflict from the file given."""
        self.__init__()
        self.file = file
        try:
            fileObj = open(file,mode='r')
        except IOError:
            print('file not readable')
            return
        try:
            self.json_import(json.load(fileObj))
        except EOFError:
            print('file is empty')
            return
        finally:
            fileObj.close()

    def recalculateFeasibleStates(self,init_override=False):
        """Updates all feasible state calculations."""
        oldFeas = list(self.feasibles.decimal)
        feasDash = ['-'*len(self.options)]
        for infeas in self.infeasibles:
            res = gmcrUtil.rmvSt(feasDash,infeas.ynd())
            feasDash = res[0]
            infeas.statesRemoved = res[1]
        self.feasibles = FeasibleList(feasDash)
        if self.feasibles.decimal != oldFeas:
            if not init_override:
                self.onFeasibleStatesChanged()
        
    def onFeasibleStatesChanged(self):
        self.useManualPreferenceRanking = False
        
        
    def clearPreferences(self):
        for dm in self.decisionMakers:
            dm.preferences.__init__(self)

    def reorderOptionsByDM(self):
        moved = []
        for dm in self.decisionMakers:
            for option in dm.options:
                if option not in moved:
                    moved.append(option)
                    self.options.insert(len(moved),self.options.pop(self.options.index(option)))
        self.options.set_indexes()
