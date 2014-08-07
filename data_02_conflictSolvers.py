# Copyright:   (c) Oskar Petersons 2013

"""Conflict analysis engines and reachability matrix generators."""

import numpy
import itertools
import json
import data_01_conflictModel as model
from tkinter import filedialog

class Preference:
    def __init__(self,preferred,oneOfSet):
        self.preferred = preferred


class RMGenerator:
    """Reachability matrix class.
    
    When initialized with a conflict for data, it produces reachability matrices
    for each of the decision makers.
    
    Key methods for extracting data from the matrix are:
    reachable(dm,state)
    uis(dm,state)
    
    Other methods are provided that allow the reachability data to be exported.
    
    """
    def __init__(self,conflict,useCoalitions=True):

        self.conflict = conflict
        
        if useCoalitions:
            if len(self.conflict.coalitions) == 0:
                for dm in self.conflict.decisionMakers:
                    self.conflict.coalitions.append(dm)
            self.effectiveDMs = self.conflict.coalitions
        else:
            self.effectiveDMs = self.conflict.decisionMakers

        for dm in self.effectiveDMs:
            dm.reachability = numpy.zeros((len(conflict.feasibles),len(conflict.feasibles)),numpy.int_)
            if dm.isCoalition:
                pmTemp = numpy.array([dm.payoffs for dm in dm]).transpose()
                pmTemp = pmTemp[numpy.newaxis,:,:] - pmTemp[:,numpy.newaxis]
                dm.payoffMatrix = (pmTemp>0).all(axis=2)
            else:
                pmTemp = numpy.array(dm.payoffs)
                dm.payoffMatrix = pmTemp[numpy.newaxis,:] - pmTemp[:,numpy.newaxis]

            # generate a flat list of move values controlled by other DMs

            otherCOsMoves = [option.dec_val for otherDM in self.effectiveDMs if otherDM!=dm for option in otherDM.options ]
            focalCOmoves = [option.dec_val for option in dm.options]

            # translate the list of moves values for other DMs into a list of base states
            fixedStates = [0]
            for val in otherCOsMoves:
                fixedStates = [y+z for y in fixedStates for z in [0, val]]

            # translate the list of focal DM move values into a list of focal DM states
            manipulatedStates = [0]
            for val in focalCOmoves:
                manipulatedStates = [y+z for y in manipulatedStates for z in [0, val]]

            # find the full set of mutually reachable states (controlled by the focal DM) for each fixed state (controlled by the other DMs)
            for state in fixedStates:
                reachable = [state]     #starting point
                reachable = [y+z for y in reachable for z in manipulatedStates]   #full reachable set
                reachable = [y for y in reachable if (y in conflict.feasibles.decimal)]   #remove infeasibles

                for state0 in reachable:    #add one set of mutually reachable states
                    s0 = self.conflict.feasibles.toOrdered[state0]-1
                    for state1 in reachable:
                        s1 = self.conflict.feasibles.toOrdered[state1]-1
                        if s0 != s1:
                            dm.reachability[s0,s1] =  1

            # Remove irreversible states ######################################################
            for option in conflict.options:
                if option.permittedDirection != "both":
                    for idx0,state0yn in enumerate(conflict.feasibles.yn):
                        # does state have potential for irreversible move?
                        val0 = state0yn[option.master_index]           # value of the irreversible move option in DMs current state (Y/N)
                        if (val0 == "Y") and (option.permittedDirection == "fwd") or (val0 == "N") and (option.permittedDirection == "back"):
                            for idx1,state1yn in enumerate(conflict.feasibles.yn):
                                #does target move have irreversible move?
                                val1 = state1yn[option.master_index]
                                if val0 != val1:
                                #remove irreversible moves from reachability matrix
                                    dm.reachability[idx0,idx1] = 0
                                        

    def reachable(self,dm,stateIdx):
        """Returns a list of all states reachable by a decisionMaker or coalition from state.
        
        dm: a DecisionMaker or Coalition that was passed to the constructor.
        stateIdx: the index of the state in the conflict.
        """
        if dm not in self.effectiveDMs:
            raise ValueError("DM or Coalition not valid.")
        reachVec = numpy.nonzero(dm.reachability[stateIdx,:])[0].tolist()
        return reachVec

    def UIs(self,dm,stateIdx,refState=None):
        """Returns a list of a unilateral improvements available to dm from state.
        
        dm: a DecisionMaker or Coalition that was passed to the constructor.
        stateIdx is the index of the state in the conflict.
        refState (optional) is another state to be used as a baseline for 
            determining whether or not a state is an improvement -- states will
            be returned as UIs only if they are reachable from stateIdx and more
            preferred from refState.
        """
        if dm not in self.effectiveDMs:
            raise ValueError("DM or Coalition not valid.")
        if refState is None:
            refState = stateIdx
        UIvec = numpy.nonzero(dm.reachability[stateIdx,:] * dm.payoffMatrix[refState,:] > 0)[0].tolist()
        return UIvec

    def saveJSON(self,file):
        """Export conflict data to JSON format for presentation.

        Includes the full normal save file, plus reachability data and payoffs.
        """
        gameData = self.conflict.export_rep()
        
        nodes = []

        for stateIdx,stateDec in enumerate(self.conflict.feasibles.decimal):
            stateYN = self.conflict.feasibles.yn[stateIdx]
            stateOrd = self.conflict.feasibles.ordered[stateIdx]
            reachable = []

            for coInd,dm in enumerate(self.effectiveDMs):
                for rchSt in self.reachable(dm,stateIdx):
                    reachable.append({'target':rchSt,
                                      'dm': 'dm%s'%coInd,
                                      'payoffChange':int(dm.payoffMatrix[stateIdx,rchSt])})
                         
            nodes.append({'id':stateIdx,
                          'decimal':str(stateDec),
                          'ordered':str(stateOrd),
                          'state':str(stateYN),
                          'reachable':reachable})
                          
        gameData["nodes"] = nodes
                                                
        with open(file,'w') as jsonfile:
            json.dump(gameData,jsonfile)


class LogicalSolver(RMGenerator):
    """Solves the games for equilibria, based on the logical definitions of stability concepts."""
    def __init__(self,conflict):
        RMGenerator.__init__(self,conflict)

    def chattyHelper(self,co,state):
        """Used in generating narration for the verbose versions of the stability calculations."""
        if co.isCoalition:
            pay = [dm.payoffs[state] for dm in co.members]
        else:
            pay  = co.payoffs[state]
        snippet = 'state %s (decimal %s, payoff %s)' %(state+1, self.conflict.feasibles.decimal[state], pay)
        return snippet


    def nash(self,dm,state0):
        """Used to calculate Nash stability. Returns true if state0 Nash is stable for dm."""
        ui=self.UIs(dm,state0)
        if not ui:
            narr = self.chattyHelper(dm,state0)+' is Nash stable for DM '+ dm.name +' since they have no UIs from this state.\n'
            return True,narr
        else:
            narr = self.chattyHelper(dm,state0)+' is NOT Nash stable for DM '+ dm.name +' since they have UIs available to: '+','.join([self.chattyHelper(dm,state1) for state1 in ui])+"\n"
            return False,narr


    def seq(self,dm,state0):
        """Used to calculate SEQ stability. Returns true if state0 is SEQ stable for dm."""
        ui=self.UIs(dm,state0)
        narr = ''

        if not ui:
            seqStab = 1      #stable since the dm has no UIs available
            narr += self.chattyHelper(dm,state0)+' is SEQ stable for DM '+ dm.name +' since they have no UIs from this state.\n'
        else:
            narr += 'From ' + self.chattyHelper(dm,state0) + ' ' + dm.name +' has UIs available to: ' + ''.join([self.chattyHelper(dm,state1) for state1 in ui]) + ' .  Check for sanctioning...\n\n'
            for state1 in ui:             #for each potential move...
                otherCOuis = [x for oCO in self.effectiveDMs if oCO != dm for x in self.UIs(oCO,state1)]     #find all possible UIs available to other players
                if not otherCOuis:
                    seqStab=0
                    narr += self.chattyHelper(dm,state0)+' is unstable by SEQ for focal DM '+dm.name+', since their opponents have no UIs from '+self.chattyHelper(dm,state1) + '\n\n'
                    return seqStab,narr
                else:
                    stable=0
                    for state2 in otherCOuis:
                        if dm.payoffMatrix[state0,state2]  <= 0:
                            stable = 1
                            narr += 'A move to '+self.chattyHelper(dm,state1)+' is SEQ sanctioned for focal DM '+ dm.name+' by a move to '+self.chattyHelper(dm,state2)+' by other dms.  Check other focal DM UIs for sanctioning... \n\n'
                            break

                    if not stable:
                        seqStab=0
                        narr += self.chattyHelper(dm,state0)+') is unstable by SEQ for focal DM ' + dm.name + ', since their opponents have no less preferred sanctioning UIs from '+self.chattyHelper(dm,state1) + '\n\n'
                        return seqStab,narr

            seqStab = 1
            narr += self.chattyHelper(dm,state0) + ' is stable by SEQ for focal dm ' + dm.name + ', since all available UIs ' + str([self.chattyHelper(dm,state1) for state1 in ui]) + ' are sanctioned by other players. \n\n'
        return seqStab,narr


    def sim(self,dm,state0):
        """Used to calculate SIM stability. Returns true if state0 is SIM stable for dm."""
        ui=self.UIs(dm,state0)
        narr=''

        if not ui:
            simStab = 1      #stable since the dm has no UIs available
            narr += self.chattyHelper(dm,state0)+' is SIM stable since focal dm ' + dm.name + ' has no UIs available.\n'
        else:
            narr += 'From ' + self.chattyHelper(dm,state0) + ' ' + dm.name +' has UIs available to: ' + ''.join([self.chattyHelper(dm,state1) for state1 in ui]) + ' .  Check for sanctioning...\n\n'
            otherDMuis = [x for oDM in self.effectiveDMs if oDM != dm for x in self.UIs(oDM,state0)]     #find all possible UIs available to other players
            if not otherDMuis:
                simStab=0
                narr += self.chattyHelper(dm,state0)+' is unstable by SIM for focal dm ' + dm.name + ', since their opponents have no UIs from '+self.chattyHelper(dm,state0) + '.\n\n'
                return simStab,narr
            else:
                for state1 in ui:
                    stable=0
                    for state2 in otherDMuis:
                        state2combinedDec = self.conflict.feasibles.decimal[state1]+self.conflict.feasibles.decimal[state2]-self.conflict.feasibles.decimal[state0]
                        if state2combinedDec in self.conflict.feasibles.decimal:
                            state2combined = self.conflict.feasibles.decimal.index(state2combinedDec)
                            if dm.payoffMatrix[state0,state2combined] <= 0:
                                stable = 1
                                narr += 'A move to '+self.chattyHelper(dm,state1)+' is SIM sanctioned for focal DM ' + dm.name + ' by a move to '+self.chattyHelper(dm,state2)+' by other DMs, which would give a final state of ' + self.chattyHelper(dm,state2combined) + '.  Check other focal DM UIs for sanctioning...\n\n'
                                break
                        else: narr += 'Simultaneous moves towards ' + str(state1) + ' and ' + str(state2) + ' are not possible since the resultant state is infeasible.\n\n'

                    if not stable:
                        simStab=0
                        narr += self.chattyHelper(dm,state0)+') is unstable by SIM for focal DM ' + dm.name + ', since their opponents have no less preferred sanctioning UIs from ' + self.chattyHelper(dm,state1) + '.\n\n'
                        return simStab,narr

            simStab = 1
            narr += self.chattyHelper(dm,state0) + ' is stable by SIM for focal DM ' + dm.name + ', since all available UIs ' + str([self.chattyHelper(dm,state1) for state1 in ui]) + ' are sanctioned by other players.\n\n'
        return simStab,narr


    def gmr(self,dm,state0):
        """Used to calculate GMR stability. Returns true if state0 is GMR stable for dm."""
        ui=self.UIs(dm,state0)
        narr=''

        if not ui:
            gmrStab = 1      #stable since the dm has no UIs available
            narr += self.chattyHelper(dm,state0)+' is GMR stable since focal DM '+dm.name+' has no UIs available.\n'
        else:
            narr += 'From ' + self.chattyHelper(dm,state0) + ' ' + dm.name +' has UIs available to: ' + ''.join([self.chattyHelper(dm,state1) for state1 in ui]) + '.   Check for sanctioning...\n\n'
            for state1 in ui:             #for each potential move...
                otherDMums = [x for oDM in self.effectiveDMs if oDM != dm for x in self.reachable(oDM,state1)]        #find all possible moves (not just UIs) available to other players
                if not otherDMums:
                    gmrStab=0
                    narr += self.chattyHelper(dm,state0)+' is unstable by GMR for focal DM '+dm.name+', since their opponents have no moves from '+self.chattyHelper(dm,state1) +'.\n\n'
                    return gmrStab,narr
                else:
                    stable=0
                    for state2 in otherDMums:
                        if dm.payoffMatrix[state0,state2] <= 0:
                            stable = 1
                            narr += 'A move to '+self.chattyHelper(dm,state1)+' is GMR sanctioned for focal DM '+dm.name+' by a move to '+self.chattyHelper(dm,state2)+' by other DMs.\n\n'
                            break

                    if not stable:
                        gmrStab=0
                        narr += self.chattyHelper(dm,state0)+') is unstable by GMR for focal dm '+dm.name+', since their opponents have no less preferred sanctioning UIs from '+self.chattyHelper(dm,state1) + '.\n\n'
                        return gmrStab,narr

            gmrStab = 1
            narr += self.chattyHelper(dm,state0) + ' is stable by GMR for focal DM '+dm.name+', since all available UIs '+str([self.chattyHelper(dm,state1) for state1 in ui])+'are sanctioned by other players.\n\n'
        return gmrStab,narr


    def smr(self,dm,state0):
        """Used to calculate SMR stability. Returns true if state0 is SMR stable for dm."""
        ui=self.UIs(dm,state0)
        narr= ''

        if not ui:
            smrStab = 1      #stable since the dm has no UIs available
            narr += self.chattyHelper(dm,state0)+' is SMR stable since focal DM '+dm.name+' has no UIs available.\n'
        else:
            narr += 'From ' + self.chattyHelper(dm,state0) + ' ' + dm.name +' has UIs available to: ' + ''.join([self.chattyHelper(dm,state1) for state1 in ui]) + ' .  Check for sanctioning...\n\n'
            for state1 in ui:             #for each potential move...
                otherDMums = [x for oDM in self.effectiveDMs if oDM != dm for x in self.reachable(oDM,state1)]        #find all possible moves (not just UIs) available to other players

                if not otherDMums:
                    smrStab=0
                    narr += self.chattyHelper(dm,state0)+' is unstable by SMR for focal DM '+dm.name+', since their opponents have no moves from '+self.chattyHelper(dm,state1) + '.\n\n'
                    return smrStab,narr
                else:
                    stable=0
                    for state2 in otherDMums:
                        if dm.payoffMatrix[state0,state2] <= 0:     # if a sanctioning state exists...
                            narr += 'A move to '+self.chattyHelper(dm,state1)+' is SMR sanctioned for focal DM '+dm.name+' by a move to '+self.chattyHelper(dm,state2)+' by other dms.  Check for possible countermoves...\n\n'
                            stable = 1
                            ui2 = self.UIs(dm,state2,state0)         # Find list of moves available to the focal DM from 'state2' with a preference higher than 'state0'

                            if ui2:     #still unstable since countermove is possible.  Check other sanctionings...
                                narr += '    The sanctioned state '+self.chattyHelper(dm,state2)+' can be countermoved to ' + str([self.chattyHelper(dm,state3) for state3 in ui2])+'. Check other sanctionings...\n\n'
                                stable =0

                            else:        #'state0' is stable since there is a sanctioning 'state2' that does not have a countermove
                                narr += '    '+self.chattyHelper(dm,state1)+' remains sanctioned under SMR for focal DM '+dm.name+', since they cannot countermove their opponent\'s sanction to '+self.chattyHelper(dm,state2) + '.\n\n'
                                break

                    if not stable:
                        smrStab=0
                        narr += self.chattyHelper(dm,state0)+') is unstable by SMR for focal dm '+dm.name+', since their opponents have no less preferred sanctioning UIs from '+self.chattyHelper(dm,state1)+' that cannot be effectively countermoved by the focal dm.\n\n'
                        return smrStab,narr

            smrStab = 1
            narr += self.chattyHelper(dm,state0) + ' is stable by SMR for focal dm '+dm.name+', since all available UIs '+str([self.chattyHelper(dm,state1) for state1 in ui])+' are sanctioned by other players and cannot be countermoved.\n\n'
        return smrStab,narr

    def findEquilibria(self):
        """Calculates the equilibrium states that exist within the conflict for each stability concept."""
            #Nash calculation
        nashStabilities = numpy.zeros((len(self.effectiveDMs),len(self.conflict.feasibles)))
        for idx,dm in enumerate(self.effectiveDMs):
            for state in range(len(self.conflict.feasibles)):
                nashStabilities[idx,state]= self.nash(dm,state)[0]

        numpy.invert(nashStabilities.astype('bool'),nashStabilities)
        self.nashEquilibria = numpy.invert(sum(nashStabilities,0).astype('bool'))


            #SEQ calculation
        seqStabilities = numpy.zeros((len(self.effectiveDMs),len(self.conflict.feasibles)))
        for idx,dm in enumerate(self.effectiveDMs):
            for state in range(len(self.conflict.feasibles)):
                seqStabilities[idx,state]= self.seq(dm,state)[0]

        numpy.invert(seqStabilities.astype('bool'),seqStabilities)
        self.seqEquilibria = numpy.invert(sum(seqStabilities,0).astype('bool'))


            #SIM calculation
        simStabilities = numpy.zeros((len(self.effectiveDMs),len(self.conflict.feasibles)))
        for idx,dm in enumerate(self.effectiveDMs):
            for state in range(len(self.conflict.feasibles)):
                simStabilities[idx,state] = self.sim(dm,state)[0]

        numpy.invert(simStabilities.astype('bool'),simStabilities)
        self.simEquilibria = numpy.invert(sum(simStabilities,0).astype('bool'))

            #SEQ + SIM calculation
        seqSimStabilities = numpy.bitwise_and(simStabilities.astype('bool'), seqStabilities.astype('bool'))
        self.seqSimEquilibria = numpy.invert(sum(seqSimStabilities,0).astype('bool'))

            #GMR calculation
        gmrStabilities = numpy.zeros((len(self.effectiveDMs),len(self.conflict.feasibles)))
        for idx,dm in enumerate(self.effectiveDMs):
            for state in range(len(self.conflict.feasibles)):
                gmrStabilities[idx,state]=self.gmr(dm,state)[0]

        numpy.invert(gmrStabilities.astype('bool'),gmrStabilities)
        self.gmrEquilibria = numpy.invert(sum(gmrStabilities,0).astype('bool'))


            #SMR calculations
        smrStabilities = numpy.zeros((len(self.effectiveDMs),len(self.conflict.feasibles)))
        for idx,dm in enumerate(self.effectiveDMs):
            for state in range(len(self.conflict.feasibles)):
                smrStabilities[idx,state]=self.smr(dm,state)[0]

        numpy.invert(smrStabilities.astype('bool'),smrStabilities)
        self.smrEquilibria = numpy.invert(sum(smrStabilities,0).astype('bool'))

        #output
        self.allEquilibria = numpy.vstack((self.nashEquilibria,
                                        self.gmrEquilibria,
                                        self.seqEquilibria,
                                        self.simEquilibria,
                                        self.seqSimEquilibria,
                                        self.smrEquilibria))


class InverseSolver(RMGenerator):
    def __init__(self,conflict,vary=None,desiredEquilibria=None):
        RMGenerator.__init__(self,conflict,useCoalitions=False)
        if type(desiredEquilibria) is list:
            self.desEq = desiredEquilibria[0]
        else:
            self.desEq = desiredEquilibria
        self.vary  = vary
        self.conflict = conflict
        
        for idx,dm in enumerate(self.conflict.decisionMakers):
            dm.improvementsInv = numpy.sign(numpy.array(dm.payoffMatrix,numpy.float64))
            if self.vary is not None:
                varyRange = self.vary[idx]
                variedStates = []
                if varyRange != [0,0]:
                    varyRange = dm.preferenceVector[varyRange[0]:varyRange[1]]
                    for sl in varyRange:
                        if type(sl) is list:
                            variedStates.extend([state-1 for state in sl])
                        else:
                            variedStates.append(sl-1)
                
                for s0 in variedStates:
                    for s1 in variedStates:
                        if s0 != s1:
                            dm.improvementsInv[s0,s1] = numpy.nan

        #dm.improvementsInv[s0,s1] indicates whether a state s0 is more preferred (+1), 
        # less preferred(-1), equally preferred(0), or has an unspecified relation (nan) to 
        # another state s1. Generated based on the vary ranges selected.

    def _decPerm(self,full,vary):
        """Returns all possible permutations of a list 'full' when only the span
        defined by 'vary' is allowed to change. (UI vector for 1 DM)."""
        if not vary:
            yield full
        else:
            for x in itertools.permutations(full[vary[0]:vary[1]]):
                yield full[:vary[0]]+list(x)+full[vary[1]:]

    def prefPermGen(self,prefVecs,vary):
        """Returns all possible permutations of the group of preference vectors
        'pref' when the spans defined in 'vary' are allowed to move for each DM."""
        b=[self._decPerm(y,vary[x]) for x,y in enumerate(prefVecs)]
        c=itertools.product(*b)
        for y in c:
            yield y
            
    def nashCond(self):
        """Generates a list of the conditions that preferences must satisfy for Nash stability to exist."""
        output=[""]
        for dmIdx,dm in enumerate(self.conflict.decisionMakers):
            desEq = self.conflict.feasibles.ordered[self.desEq]
            mblNash = [self.conflict.feasibles.ordered[state] for state in self.mustBeLowerNash[dmIdx]]
            if len(mblNash)>0:
                message = "For DM %s: %s must be more preferred than %s"%(dm.name,desEq,mblNash)
            else:
                message = "For DM %s: Always stable as there are no moves from %s"%(dm.name,desEq)
            output.append(message)
            if self.vary is not None:
                output.append("    With the given preference rankings and vary range:")
                message1 = ''
                for state1 in self.mustBeLowerNash[dmIdx]:
                    if numpy.isnan(dm.improvementsInv[self.desEq,state1]):
                        message1 += "    %s must be more preferred than %s.\n"%(desEq,self.conflict.feasibles.ordered[state1])
                    elif dm.improvementsInv[self.desEq,state1] == 1:
                        message1 = "    Equilibrium not possible as %s is always more preferred than %s"%(self.conflict.feasibles.ordered[state1],desEq)
                        break
                if message1 == '':
                    message1 = "    equilibrium exists under all selected rankings"
                output.append(message1)
        return "\n\n".join(output)+"\n\n\n\n"
        
    def gmrCond(self):
        """Generates a list of the conditions that preferences must satisfy for GMR stability to exist."""
        output=[""]
        for dmIdx,dm in enumerate(self.conflict.decisionMakers):
            desEq = self.conflict.feasibles.ordered[self.desEq]
            mblGMR = [self.conflict.feasibles.ordered[state] for state in self.mustBeLowerNash[dmIdx]]
            mbl2GMR = []
            for stateList in self.mustBeLowerGMR[dmIdx]:
                mbl2GMR.extend(stateList)
            mbl2GMR = list(set(mbl2GMR))
            mbl2GMR = [self.conflict.feasibles.ordered[state] for state in mbl2GMR] 
            message = "For DM %s: %s must be more preferred than %s"%(dm.name,desEq,mblGMR)
            message += "\n\n  or at least one of %s must be less preferred than %s"%(mbl2GMR,desEq)
            output.append(message)
            if self.vary is not None:
                output.append("    With the given preference rankings and vary range:")
                message1 = ''
                for idx1,state1 in enumerate(self.mustBeLowerNash[dmIdx]):
                    if numpy.isnan(dm.improvementsInv[self.desEq,state1]):
                        isLower = []
                        isOpen = []
                        for state2 in self.mustBeLowerGMR[dmIdx][idx1]:
                            if numpy.isnan(dm.improvementsInv[self.desEq,state2]):
                                isOpen.append(state2)
                            elif dm.improvementsInv[self.desEq,state2] <= 0:
                                isLower.append(state2)
                        if isLower != []:
                            continue
                        elif isOpen != []:
                            message1 += "    at least one of [%s, %s] must be less preferred than %s\n"%(
                                self.conflict.feasibles.ordered[state1],
                                str([self.conflict.feasibles.ordered[st] for st in isOpen])[1:-1],
                                desEq)
                    elif dm.improvementsInv[self.desEq,state1] ==1:
                        isLower = []
                        isOpen = []
                        for state2 in self.mustBeLowerGMR[dmIdx][idx1]:
                            if numpy.isnan(dm.improvementsInv[self.desEq,state2]):
                                isOpen.append(state2)
                            elif dm.improvementsInv[self.desEq,state2] <= 0:
                                isLower.append(state2)
                        if isLower != []:
                            continue
                        elif isOpen != []:
                            message1 += "    at least one of %s must be less preferred than %s\n"%(
                                [self.conflict.feasibles.ordered[st] for st in isOpen],
                                desEq)
                if message1 == '':
                    message1 = "    equilibrium exists under all selected rankings"
                output.append(message1)
        return "\n\n".join(output)

    def seqCond(self):
        """Generates a list of the conditions that preferences must satisfy for SEQ stability to exist."""
        output=[""]
        for dmIdx,dm in enumerate(self.conflict.decisionMakers):
            desEq = self.conflict.feasibles.ordered[self.desEq]
            mblSEQ = [self.conflict.feasibles.ordered[state] for state in self.mustBeLowerNash[dmIdx]]
            message = "For DM %s: %s must be more preferred than %s"%(dm.name,desEq,mblSEQ)
            for dmIdx2 in range(len(self.conflict.decisionMakers)):
                if dmIdx2 == dmIdx:
                    continue
                for state1 in self.mustBeLowerNash[dmIdx]:
                    for state2 in self.reachable(self.conflict.decisionMakers[dmIdx2],state1):
                        s1 = self.conflict.feasibles.ordered[state1]
                        s2 = self.conflict.feasibles.ordered[state2]
                        message += "\n\n  or if %s is preferred to %s for DM %s, %s must be less preferred than %s for DM %s"%(s2,s1,self.conflict.decisionMakers[dmIdx2].name,s2,desEq,dm.name)
            output.append(message)
            if self.vary is not None:
                output.append("    With the given preference rankings and vary range:")
                message1 = ''
                for idx1,state1 in enumerate(self.mustBeLowerNash[dmIdx]):
                    if numpy.isnan(dm.improvementsInv[self.desEq,state1]):
                        isLower1 = []
                        isOpen1 = []
                        for state2 in self.mustBeLowerGMR[dmIdx][idx1]:
                            if numpy.isnan(dm.improvementsInv[self.desEq,state2]):
                                isOpen1.append(state2)
                            elif dm.improvementsInv[self.desEq,state2] <= 0:
                                isLower1.append(state2)
                        if isLower1 != []:
                            continue
                        elif isOpen1 != []:
                            message2 = "    %s must be less preferred than %s\n"%(
                                self.conflict.feasibles.ordered[state1], desEq)
                            for dmIdx2 in range(len(self.conflict.decisionMakers)):
                                if dmIdx2 == dmIdx:
                                    continue
                                for state2 in self.reachable(self.conflict.decisionMakers[dmIdx2],state1):
                                    if numpy.isnan(self.conflict.decisionMakers[dmIdx2].improvementsInv[state1,state2]):
                                        message2 += "    OR %s must be preferred to %s by %s AND %s must be less preferred than %s by %s\n"%(
                                            self.conflict.feasibles.ordered[state2],
                                            self.conflict.feasibles.ordered[state1],
                                            self.conflict.decisionMakers[dmIdx2].name,
                                            self.conflict.feasibles.ordered[state2],
                                            desEq,
                                            self.conflict.decisionMakers[dmIdx].name)
                                    elif self.conflict.decisionMakers[dmIdx2].improvementsInv[state1,state2] == 1:
                                        message2 = ""
                            message1 += message2

                    elif dm.improvementsInv[self.desEq,state1] ==1:
                        isLower1 = []
                        isOpen1 = []
                        for state2 in self.mustBeLowerGMR[dmIdx][idx1]:
                            if numpy.isnan(dm.improvementsInv[self.desEq,state2]):
                                isOpen1.append(state2)
                            elif dm.improvementsInv[self.desEq,state2] <= 0:
                                isLower1.append(state2)
                        if isLower1 != []:
                            continue
                        elif isOpen1 != []:
                            message2 = "    %s must be less preferred than %s\n"%(
                                self.conflict.feasibles.ordered[state1], desEq)
                            for dmIdx2 in range(len(self.conflict.decisionMakers)):
                                if dmIdx2 == dmIdx:
                                    continue
                                for state2 in self.reachable(self.conflict.decisionMakers[dmIdx2],state1):
                                    if numpy.isnan(self.conflict.decisionMakers[dmIdx2].improvementsInv[state1,state2]):
                                        message2 += "    OR %s must be preferred to %s by %s AND %s must be less preferred than %s by %s\n"%(
                                            self.conflict.feasibles.ordered[state2],
                                            self.conflict.feasibles.ordered[state1],
                                            self.conflict.decisionMakers[dmIdx2].name,
                                            self.conflict.feasibles.ordered[state2],
                                            desEq,
                                            self.conflict.decisionMakers[dmIdx].name)
                                    elif self.conflict.decisionMakers[dmIdx2].improvementsInv[state1,state2] == 1:
                                        message2 = ""
                            message1 += message2
                if message1 == '':
                    message1 = "    equilibrium exists under all selected rankings"
                output.append(message1)
        return "\n\n".join(output)
        

    def _mblInit(self):
        """Used internally to initialize the 'Must Be Lower' arrays used in inverse calculation."""
        self.mustBeLowerNash = [self.reachable(dm,self.desEq) for dm in self.conflict.decisionMakers]
        #mustBeLowerNash[dm] contains the states that must be less preferred than the 
        # desired equilibrium 'state0' for 'dm' to have a Nash equilibrium at 'state0'.

        self.mustBeLowerGMR = [[[] for state1 in dm] for dm in self.mustBeLowerNash]
        #mustBeLowerGMR[dm][idx] contains the states that 'dm' could be sanctioned to after taking
        # the move in 'idx' from 'state0'. If, for each 'idx' there is at least one state less preferred
        # than 'state0', then 'state0' is GMR.  Sanctions are UMs for opponents, but not necessarily UIs.

        for y,dm in enumerate(self.mustBeLowerNash):      #'dm' contains a list of reachable states for dm from 'state0'
            for z,state1 in enumerate(dm):
                for dm2 in range(len(self.conflict.decisionMakers)):
                    if y != dm2:
                        self.mustBeLowerGMR[y][z]+= self.reachable(self.conflict.decisionMakers[dm2],state1)

        #seq check uses same 'mustBeLower' as GMR, as sanctions are dependent on the UIs available to
        # opponents, and as such cannot be known until the preference vectors are set.

        self.mustBeLowerSMR = [[[[] for idx in state1] for state1 in dm] for dm in self.mustBeLowerGMR]
        #mustBeLowerSMR[dm][idx][idx2] contains the states that 'dm' could countermove to
        # if sanction 'idx2' was taken by opponents after 'dm' took move 'idx' from 'state0'.
        # if at least one state is more preferred that 'state0' for each 'idx2', then the state is
        # not SMR for 'dm'.

        for y,dm in enumerate(self.mustBeLowerGMR):
            for z,idx in enumerate(dm): #idx contains a list of
                self.mustBeLowerSMR[y][z] = [self.reachable(self.conflict.decisionMakers[y],state2) for state2 in idx]


    def findEquilibria(self):
        """Generates a list of all requested preference vectors, then checks if they meet equilibrium requirements."""
        self._mblInit()
        self.preferenceVectors = list(self.prefPermGen([dm.preferenceVector for dm in self.conflict.decisionMakers],self.vary))
        self.nash  = numpy.ones((len(self.preferenceVectors),len(self.conflict.decisionMakers))).astype('bool')
        self.gmr   = numpy.zeros((len(self.preferenceVectors),len(self.conflict.decisionMakers))).astype('bool')
        self.seq   = numpy.zeros((len(self.preferenceVectors),len(self.conflict.decisionMakers))).astype('bool')
        self.smr   = numpy.zeros((len(self.preferenceVectors),len(self.conflict.decisionMakers))).astype('bool')

        for prefsIdx,prefsX in enumerate(self.preferenceVectors):
            payoffs =[[0]*len(self.conflict.feasibles) for x in range(len(self.conflict.decisionMakers))]

            for dm in range(len(self.conflict.decisionMakers)):
                for i,y in enumerate(prefsX[dm]):
                    try:
                        for z in y:
                            payoffs[dm][z-1] = len(self.conflict.feasibles) - i
                    except TypeError:
                        payoffs[dm][y-1] = len(self.conflict.feasibles) - i
            #check if Nash
            for dm in range(len(self.conflict.decisionMakers)):
                if not self.nash[prefsIdx,dm]: break
                pay0=payoffs[dm][self.desEq]        #payoff of the original state; higher is better
                for pay1 in (payoffs[dm][state1] for state1 in self.mustBeLowerNash[dm]):    #get preferences of all states reachable by 'dm'
                    if pay0<pay1:       #prefs0>prefs1 means a UI exists
                        self.nash[prefsIdx,dm]=False
                        break

            #check if GMR
            self.gmr[prefsIdx,:]=self.nash[prefsIdx,:]

            for dm in range(len(self.conflict.decisionMakers)):
                if self.nash[prefsIdx,dm]:
                    continue
                pay0=payoffs[dm][self.desEq]
                for state1p,state1d in enumerate(self.mustBeLowerNash[dm]):
                    pay1 = payoffs[dm][state1d]
                    if pay0<pay1:   #if there is a UI available
                        #nash=False
                        self.gmr[prefsIdx,dm]=False
                        for pay2 in (payoffs[dm][state2] for state2 in self.mustBeLowerGMR[dm][state1p]):
                            if pay0>pay2:       #if initial state was preferred to sanctioned state
                                self.gmr[prefsIdx,dm]=True
                                break

            #check if SEQ
            mustBeLowerSEQ = [[[] for state1 in dm] for dm in self.mustBeLowerNash]

            for y,dm in enumerate(self.mustBeLowerNash):
                for z,state1 in enumerate(dm):
                    for dm2 in range(len(self.conflict.decisionMakers)):
                        if y != dm2:
                            mustBeLowerSEQ[y][z]+=[state2 for state2 in self.reachable(self.conflict.decisionMakers[dm2],state1) if payoffs[dm2][state2]>payoffs[dm2][state1]]

            self.seq[prefsIdx,:]=self.nash[prefsIdx,:]

            for dm in range(len(self.conflict.decisionMakers)):
                if self.nash[prefsIdx,dm]:
                    continue
                pay0=payoffs[dm][self.desEq]
                for state1p,state1d in enumerate(self.mustBeLowerNash[dm]):
                    pay1 = payoffs[dm][state1d]
                    if pay0<pay1:  #if there is a UI available
                        #nash=False
                        self.seq[prefsIdx,dm]=False
                        for pay2 in (payoffs[dm][state2] for state2 in mustBeLowerSEQ[dm][state1p]):
                            if pay0>pay2:       #if initial state was preferred to sanctioned state
                                self.seq[prefsIdx,dm]=True        #set to true since sanctioned, however this will be broken if another UI exists.
                                break

            #check if SMR
            self.smr[prefsIdx,:]=self.nash[prefsIdx,:]

            for dm in range(len(self.conflict.decisionMakers)):
                if self.nash[prefsIdx,dm]:
                    continue
                pay0=payoffs[dm][self.desEq]
                for state1p,state1d in enumerate(self.mustBeLowerNash[dm]):
                    pay1 = payoffs[dm][state1d]
                    if pay0<pay1:   #if there is a UI available
                        #nash=False
                        self.smr[prefsIdx,dm]=False
                        for state2p,state2d in enumerate(self.mustBeLowerGMR[dm][state1p]):
                            pay2 = payoffs[dm][state2d]
                            if pay0>pay2:       #if initial state was preferred to sanctioned state
                                self.smr[prefsIdx,dm]=True        #set to true since sanctioned, however this will be broken if another UI exists, or if dm can countermove.
                                for pay3 in (payoffs[dm][state3] for state3 in self.mustBeLowerSMR[dm][state1p][state2p]):
                                    if pay0<pay3:       #if countermove is better than original state.
                                        self.smr[prefsIdx,dm]=False
                                        break
                                break       #check this

        self.equilibriums = numpy.vstack((self.nash.all(axis=1),self.seq.all(axis=1),self.gmr.all(axis=1),self.smr.all(axis=1)))

    def filter(self,filt):
        values = []
        for pVeci,prefVec in enumerate(self.preferenceVectors):
            eqms = self.equilibriums[:,pVeci]
            if numpy.greater_equal(eqms,filt).all():
                values.append(tuple(list(prefVec)+[bool(x) for x in eqms]))
        counts = self.equilibriums.sum(axis=1)
        return values,counts

        
class GoalSeeker(RMGenerator):
    def __init__(self,conflict,goals=[]):
        RMGenerator.__init__(self,conflict)
        self.conflict = conflict
        self.goals = goals
        
    def validGoals(self):
        if len(self.goals)==0:
            return False
        for g in self.goals:
            if g[0] == -1:
                return False
            if g[1] == -1:
                return False
        return True
        
    def nash(self):
        requirements = Requirements("Conditions for goals using Nash:","AND", *[self.nashGoal(s0,stable) for s0,stable in self.goals])
        return requirements
        
    def seq(self):
        requirements = Requirements("Conditions for goals using SEQ:","AND", *[self.seqGoal(s0,stable) for s0,stable in self.goals])
        return requirements

    def nashGoal(self,state0,stable):
        """Generates a list of the conditions that preferences must satisfy for state0 to be stable/unstable by Nash."""
        if stable:
            conditions = Requirements("For %s to be stable by Nash:"%(state0+1),"AND")
        else:
            conditions = Requirements("For %s to be unstable by Nash:"%(state0+1),"OR")
        
        for coIdx,co in enumerate(self.effectiveDMs):
            if stable:
                for state1 in self.reachable(co,state0):
                    conditions.append(MoreThanFor(co,state0,state1))
            else:
                if self.reachable(co,state0):
                    conditions.append(LessThanOneOf(co,state0,self.reachable(co,state0)))
        
        return conditions

    def seqGoal(self,state0,stable):
        """Generates a list of the conditions that preferences must satisfy for state0 to be stable/unstable by SEQ."""
        conditions = Requirements("For %s to be %s by SEQ:"%(state0+1,"stable" if stable else "unstable"),"AND")
        
        for coIdx,co in enumerate(self.effectiveDMs):
            if stable:
                for state1 in self.reachable(co,state0):
                    isNash = MoreThanFor(co,state0,state1)
                    isStable = PatternOr(isNash)
                    
                    for coIdx2,co2 in enumerate(self.effectiveDMs):
                        if coIdx2 == coIdx:
                            continue
                        for state2 in self.reachable(self.effectiveDMs[coIdx2],state1):
                            isSanctioned = PatternAnd(MoreThanFor(co2,state2, state1),MoreThanFor(co,state0,state2))
                            isStable.append(isSanctioned)
                    conditions.append(isStable)
            else:
                isUnstable = PatternOr()
                for state1 in self.reachable(co,state0):
                    isUI = MoreThanFor(co,state1,state0)
                    isUnsanctionedUI = PatternAnd(isUI)
                    isUnstable.append(isUnsanctionedUI)
                    for coIdx2,co2 in enumerate(self.effectiveDMs):
                        if coIdx2 == coIdx:
                            continue
                        for state2 in self.reachable(self.effectiveDMs[coIdx2],state1):
                            notASanction = PatternOr(MoreThanFor(co2,state1,state2),MoreThanFor(co,state2,state0))
                            isUnsanctionedUI.append(notASanction)
                if len(isUnstable.plist) > 0:
                    conditions.append(isUnstable)
        return conditions
        

        
class Requirements:
    """Holds patterns/conditions and a statement of what they define."""
    def __init__(self,statement,betweenConditions,*patterns):
        self.statement = statement
        self.plist = list(patterns)
        self.betweenConditions = betweenConditions
        
    def append(self,p):
        self.plist.append(p)
        
    def asString(self,indent=""):
        patterns = [p.asString(indent+" |") for p in self.plist]
        return indent+self.statement+"\n"+(indent+self.betweenConditions+"\n").join(patterns)
    
class PatternAnd:
    """All statements must be true."""
    def __init__(self,*patterns):
        self.plist = list(patterns)
        
    def append(self,p):
        self.plist.append(p)
        
    def asString(self,indent=""):
        patterns = [p.asString(indent+" |") for p in self.plist]
        return (indent+"AND\n").join(patterns)

class PatternOr:
    """At least one statement must be true."""
    def __init__(self,*patterns):
        self.plist = list(patterns)
        
    def append(self,p):
        self.plist.append(p)
        
    def asString(self,indent=""):
        patterns = [p.asString(indent+" |") for p in self.plist]
        return (indent+"OR\n").join(patterns)

class MoreThanFor:
    """s0 must be more preferred than s1 for co."""
    def __init__(self,co,s0,s1):
        self.co = co
        self.s0 = s0
        self.s1 = s1
        
    def asString(self,indent=""):
        return indent+"%s must be more preferred than %s for %s\n"%(self.s0+1,self.s1+1,self.co.name)

class LessThanOneOf:
    """s0 must be less preferred than at least one of the states in li for co."""
    def __init__(self,co,s0,li):
        self.co = co
        self.s0 = s0
        self.li = li
        
    def asString(self,indent=""):
        return indent+"%s must be less preferred than at least one of %s for %s\n"%(self.s0+1,[s1+1 for s1 in self.li],self.co.name)



class MatrixCalc(RMGenerator):
    def __init__(self,conflict):
        RMGenerator.__init__(conflict)






def main():
    from data_01_conflictModel import ConflictModel
    g1 = ConflictModel('Prisoners.gmcr')

    rms = LogicalSolver(g1)


if __name__ == '__main__':
    main()
