import numpy
import itertools
import json

class RMGenerator:
    """Reachability matrix class.
    
    When initialized with a game for data, it produces a reachability matrix
    for it.  
    
    Key methods for extracting data from the matrix are:
    reachable(dm,state)
    uis(dm,state)
    
    Other methods are provided that allow the reachability data to be exported.
    
    """
    def __init__(self,game):

        self.game = game
        
        for option in self.game.options:
            print(option.name,option.dec_val)

        for dm in self.game.decisionMakers:
        
            dm.reachability = numpy.empty((len(game.feasibles),len(game.feasibles)))
            dm.reachability.fill(numpy.nan)

            # generate a flat list of move values controlled by other DMs

            otherDMsMoves = [option.dec_val for otherDM in self.game.decisionMakers if otherDM!=dm for option in otherDM.options ]
            focalDMmoves = [option.dec_val for option in dm.options]
            print(dm.name,focalDMmoves,otherDMsMoves)

            # translate the list of moves values for other DMs into a list of base states
            fixedStates = [0]
            for val in otherDMsMoves:
                fixedStates = [y+z for y in fixedStates for z in [0, val]]

            # translate the list of focal DM move values into a list of focal DM states
            manipulatedStates = [0]
            for val in focalDMmoves:
                manipulatedStates = [y+z for y in manipulatedStates for z in [0, val]]

            # find the full set of mutually reachable states (controlled by the focal DM) for each fixed state (controlled by the other DMs)
            for state in fixedStates:
                reachable = [state]     #starting point
                reachable = [y+z for y in reachable for z in manipulatedStates]   #full reachable set
                reachable = [y for y in reachable if (y in game.feasibles.decimal)]   #remove infeasibles

                for state0 in reachable:    #add one set of mutually reachable states
                    s0 = self.game.feasibles.toOrdered[state0]-1
                    for state1 in reachable:
                        s1 = self.game.feasibles.toOrdered[state1]-1
                        if s0 != s1:
                            dm.reachability[s0,s1] =  dm.payoffs[s1]

        # Remove irreversible states ######################################################
            UseIrreversibles = True
            if UseIrreversibles:
                for option in game.options:
                    if option.permittedDirection != "both":
                        for idx0,state0yn in enumerate(game.feasibles.yn):
                            # does state have potential for irreversible move?
                            val0 = state0yn[option.master_index]           # value of the irreversible move option in DMs current state (Y/N)
                            if (val0 == "Y") and (option.permittedDirection == "fwd") or (val0 == "N") and (option.permittedDirection == "back"):
                                for idx1,state1yn in enumerate(game.feasibles.yn):
                                    #does target move have irreversible move?
                                    val1 = state1yn[option.master_index]
                                    if val0 != val1:
                                    #remove irreversible moves from reachability matrix
                                        dm.reachability[idx0,idx1]= numpy.nan

    def reachable(self,dm,stateIdx):
        """Returns a list of all states reachable by dm from state.
        
        dm a DecisionMaker object.
        stateIdx is the index of the state in the game.
        """
        reachVec = numpy.isfinite(dm.reachability[stateIdx,:]).nonzero()[0].tolist()
        return reachVec

    def UIs(self,dm,stateIdx,minPref=None):
        """Returns a list of a unilateral improvements available to dm from state
        
        dm is the integer index of the decision maker.
        stateIdx is the index of the state in the game.
        minPref (optional) is a minimum preference for UIs to be returned. This
            is used to find moves that are preferred relative to some other
            initial state rather than the current one.  Used in SMR calculation.
        """
        UIvec = dm.reachability[stateIdx,:].flatten().tolist()

        if minPref is not None:
            UIvec = [i for i,x in enumerate(UIvec) if x>minPref]
        else:
            UIvec = [i for i,x in enumerate(UIvec) if x>dm.payoffs[stateIdx]]

        return UIvec

    def gameName(self):
        """Extracts a guess at the game's name from the file name.
        
        Used in generating file names for data dumps (json or npz).
        """
        gameName = self.game.file[::-1]
        try:
            slashInd = gameName.index('/')
            gameName = gameName[:slashInd]
        except ValueError:
            pass

        return(gameName[::-1].strip('.gmcr'))

    def saveMatrices(self):
        """Export reachability matrix to numpy format."""
        numpy.savez("RMs_for_"+self.gameName(),*self.reachabilityMatrices)

    def saveJSON(self):
        """Export conflict data to JSON format for presentation.
        
        Includes:
        Nodes: state data,
        DMs: Decision Maker Names,
        options: option names,
        startNode: the first feasible state in the game
        """
        nodes = {}
        dms = self.game.dmList
        options = self.game.getFlatOpts()
        startNode = self.game.getFeas('dec')[0]

        for stateDec,stateYN in zip(self.game.getFeas('dec'),
                                    self.game.getFeas('YN')):

            nodes[str(stateDec)] = ({'id':str(stateDec),'state':str(stateYN),
                          'ordered':str(self.game.feasibles.toOrdered[stateDec]),
                          'reachable':[]})

            for dmInd,dm in enumerate(self.game.dmList):
                for rchSt in self.reachable(dmInd,stateDec):
                    nodes[str(stateDec)]['reachable'].append(
                        {'target':str(rchSt),
                         'dm': 'dm%s'%dmInd,
                         'payoff':self.game.payoffs[dmInd][rchSt]-self.game.payoffs[dmInd][stateDec]})

        with open("networkfor_%s.json"%(self.gameName()),'w') as jsonfile:
            json.dump({"nodes":nodes,"DMs":dms,"options":options,
                       "startNode":startNode},jsonfile)


class LogicalSolver(RMGenerator):
    """Solves the games for equilibria, based on the logical definitions of stability concepts.
    
    """
    def __init__(self,game):
        RMGenerator.__init__(self,game)

    def chattyHelper(self,dm,state):
        """Used in generating narration for the verbose versions of the stability calculations"""
        snippet = 'state %s (decimal %s, payoff %s)' %(state+1, self.game.feasibles.decimal[state], dm.payoffs[state])
        return snippet


    def nash(self,dm,state):
        """Used to calculate Nash stability. Returns true if state Nash is stable for dm."""
        ui=self.UIs(dm,state)
        if not ui:
            narr = self.chattyHelper(dm,state)+' is Nash stable for DM '+ dm.name +' since they have no UIs from this state.'
            return True,narr
        else:
            narr = self.chattyHelper(dm,state)+' is NOT Nash stable for DM '+ dm.name +' since they have UIs available to: '+','.join([self.chattyHelper(dm,state1) for state1 in ui])
            return False,narr


    def seq(self,dm,state):
        """Used to calculate SEQ stability. Returns true if state is SEQ stable for dm."""
        ui=self.UIs(dm,state)
        narr = ''

        if not ui:
            seqStab = 1      #stable since the dm has no UIs available
            narr += self.chattyHelper(dm,state)+' is SEQ stable since focal DM '+ dm.name +' has no UIs available.\n\n'
        else:
            narr += 'From ' + self.chattyHelper(dm,state) + ' ' + dm.name +' has UIs available to: ' + ''.join([self.chattyHelper(dm,state1) for state1 in ui]) + ' .  Check for sanctioning...\n\n'
            for state1 in ui:             #for each potential move...
                otherDMuis = [x for oDM in self.game.decisionMakers if oDM != dm for x in self.UIs(oDM,state1)]     #find all possible UIs available to other players
                if not otherDMuis:
                    seqStab=0
                    narr += self.chattyHelper(dm,state)+' is unstable by SEQ for focal DM '+dm.name+', since their opponents have no UIs from '+self.chattyHelper(dm,state1) + '\n\n'
                    return seqStab,narr
                else:
                    stable=0
                    for state2 in otherDMuis:
                        if dm.payoffs[state2] <= dm.payoffs[state]:
                            stable = 1
                            narr += 'A move to '+self.chattyHelper(dm,state1)+' is SEQ sanctioned for focal DM '+ dm.name+' by a move to '+self.chattyHelper(dm,state2)+' by other dms.  Check other focal DN UIs for sanctioning... \n\n'
                            break

                    if not stable:
                        seqStab=0
                        narr += self.chattyHelper(dm,state)+') is unstable by SEQ for focal DM ' + dm.name + ', since their opponents have no less preferred sanctioning UIs from '+self.chattyHelper(dm,state1) + '\n\n'
                        return seqStab,narr

            seqStab = 1
            narr += self.chattyHelper(dm,state) + ' is stable by SEQ for focal dm ' + dm.name + ', since all available UIs ' + str([self.chattyHelper(dm,state1) for state1 in ui]) + ' are sanctioned by other players. \n\n'
        return seqStab,narr


    def sim(self,dm,state):
        """Used to calculate SIM stability. Returns true if state is SIM stable for dm."""
        ui=self.UIs(dm,state)
        narr=''

        if not ui:
            simStab = 1      #stable since the dm has no UIs available
            narr += self.chattyHelper(dm,state)+' is SIM stable since focal dm ' + dm.name + ' has no UIs available.\n\n'
        else:
            narr += 'From ' + self.chattyHelper(dm,state) + ' ' + dm.name +' has UIs available to: ' + ''.join([self.chattyHelper(dm,state1) for state1 in ui]) + ' .  Check for sanctioning...\n\n'
            otherDMuis = [x for oDM in self.game.decisionMakers if oDM != dm for x in self.UIs(oDM,state)]     #find all possible UIs available to other players
            if not otherDMuis:
                simStab=0
                narr += self.chattyHelper(dm,state)+' is unstable by SIM for focal dm ' + dm.name + ', since their opponents have no UIs from '+self.chattyHelper(dm,state) + '.\n\n'
                return simStab,narr
            else:
                for state1 in ui:
                    stable=0
                    for state2 in otherDMuis:
                        state2combinedDec = self.game.feasibles.decimal[state1]+self.game.feasibles.decimal[state2]-self.game.feasibles.decimal[state]
                        if state2combinedDec in self.game.feasibles.decimal:
                            state2combined = self.game.feasibles.decimal.index(state2combinedDec)
                            if dm.payoffs[state2combined] <= dm.payoffs[state]:
                                stable = 1
                                narr += 'A move to '+self.chattyHelper(dm,state1)+' is SIM sanctioned for focal DM ' + dm.name + ' by a move to '+self.chattyHelper(dm,state2)+' by other DMs, which would give a final state of ' + self.chattyHelper(dm,state2combined) + '.  Check other focal DM UIs for sanctioning...\n\n'
                                break
                        else: narr += 'Simultaneous moves towards ' + str(state1) + ' and ' + str(state2) + ' are not possible since the resultant state is infeasible.\n\n'

                    if not stable:
                        simStab=0
                        narr += self.chattyHelper(dm,state)+') is unstable by SIM for focal DM ' + dm.name + ', since their opponents have no less preferred sanctioning UIs from ' + self.chattyHelper(dm,state1) + '.\n\n'
                        return simStab,narr

            simStab = 1
            narr += self.chattyHelper(dm,state) + ' is stable by SIM for focal DM ' + dm.name + ', since all available UIs ' + str([self.chattyHelper(dm,state1) for state1 in ui]) + ' are sanctioned by other players.\n\n'
        return simStab,narr


    def gmr(self,dm,state):
        """Used to calculate GMR stability. Returns true if state is GMR stable for dm."""
        ui=self.UIs(dm,state)
        narr=''

        if not ui:
            gmrStab = 1      #stable since the dm has no UIs available
            narr += self.chattyHelper(dm,state)+' is GMR stable since focal DM '+dm.name+' has no UIs available.\n\n'
        else:
            narr += 'From ' + self.chattyHelper(dm,state) + ' ' + dm.name +' has UIs available to: ' + ''.join([self.chattyHelper(dm,state1) for state1 in ui]) + '.   Check for sanctioning...\n\n'
            for state1 in ui:             #for each potential move...
                otherDMums = [x for oDM in self.game.decisionMakers if oDM != dm for x in self.reachable(oDM,state1)]        #find all possible moves (not just UIs) available to other players
                print(state,state1)
                print(self.reachable(self.game.decisionMakers[1],state1))
                print([oDM.name for oDM in self.game.decisionMakers if oDM != dm for x in self.reachable(oDM,state1)])
                if not otherDMums:
                    gmrStab=0
                    narr += self.chattyHelper(dm,state)+' is unstable by GMR for focal DM '+dm.name+', since their opponents have no moves from '+self.chattyHelper(dm,state1) +'.\n\n'
                    return gmrStab,narr
                else:
                    stable=0
                    for state2 in otherDMums:
                        if dm.payoffs[state2] <= dm.payoffs[state]:
                            stable = 1
                            narr += 'A move to '+self.chattyHelper(dm,state1)+' is GMR sanctioned for focal DM '+dm.name+' by a move to '+self.chattyHelper(dm,state2)+' by other DMs.\n\n'
                            break

                    if not stable:
                        gmrStab=0
                        narr += self.chattyHelper(dm,state)+') is unstable by GMR for focal dm '+dm.name+', since their opponents have no less preferred sanctioning UIs from '+self.chattyHelper(dm,state1) + '.\n\n'
                        return gmrStab,narr

            gmrStab = 1
            narr += self.chattyHelper(dm,state) + ' is stable by GMR for focal DM '+dm.name+', since all available UIs '+str([self.chattyHelper(dm,state1) for state1 in ui])+'are sanctioned by other players.\n\n'
        return gmrStab,narr


    def smr(self,dm,state):
        """Used to calculate SMR stability. Returns true if state is SMR stable for dm."""
        ui=self.UIs(dm,state)
        narr= ''

        if not ui:
            smrStab = 1      #stable since the dm has no UIs available
            narr += self.chattyHelper(dm,state)+' is SMR stable since focal DM '+dm.name+' has no UIs available.\n\n'
        else:
            narr += 'From ' + self.chattyHelper(dm,state) + ' ' + dm.name +' has UIs available to: ' + ''.join([self.chattyHelper(dm,state1) for state1 in ui]) + ' .  Check for sanctioning...\n\n'
            for state1 in ui:             #for each potential move...
                otherDMums = [x for oDM in self.game.decisionMakers if oDM != dm for x in self.reachable(oDM,state1)]        #find all possible moves (not just UIs) available to other players

                if not otherDMums:
                    smrStab=0
                    narr += self.chattyHelper(dm,state)+' is unstable by SMR for focal DM '+dm.name+', since their opponents have no moves from '+self.chattyHelper(dm,state1) + '.\n\n'
                    return smrStab,narr
                else:
                    stable=0
                    for state2 in otherDMums:
                        if dm.payoffs[state2] <= dm.payoffs[state]:     # if a sanctioning state exists...
                            narr += 'A move to '+self.chattyHelper(dm,state1)+' is SMR sanctioned for focal DM '+dm.name+' by a move to '+self.chattyHelper(dm,state2)+' by other dms.  Check for possible countermoves...\n\n'
                            stable = 1
                            ui2 = self.UIs(dm,state2,dm.payoffs[state])         # Find list of moves available to the focal DM from 'state2' with a preference higher than 'state'

                            if ui2:     #still unstable since countermove is possible.  Check other sanctionings...
                                narr += '    The sanctioned state '+self.chattyHelper(dm,state2)+' can be countermoved to ' + str([self.chattyHelper(dm,state3) for state3 in ui2])+'. Check other sanctionings...\n\n'
                                stable =0

                            else:        #'state' is stable since there is a sanctioning 'state2' that does not have a countermove
                                narr += '    '+self.chattyHelper(dm,state1)+' remains sanctioned under SMR for focal DM '+dm.name+', since they cannot countermove their opponent\'s sanction to '+self.chattyHelper(dm,state2) + '.\n\n'
                                break

                    if not stable:
                        smrStab=0
                        narr += self.chattyHelper(dm,state)+') is unstable by SMR for focal dm '+dm.name+', since their opponents have no less preferred sanctioning UIs from '+self.chattyHelper(dm,state1)+' that cannot be effectively countermoved by the focal dm.\n\n'
                        return smrStab,narr

            smrStab = 1
            narr += self.chattyHelper(dm,state) + ' is stable by SMR for focal dm '+dm.name+', since all available UIs '+str([self.chattyHelper(dm,state1) for state1 in ui])+' are sanctioned by other players and cannot be countermoved.\n\n'
        return smrStab,narr

    def findEquilibria(self):
        """Calculates the equalibrium states that exist within the game for each stability concept."""
        print("calculating equilibria...")
            #Nash calculation
        nashStabilities = numpy.zeros((len(self.game.decisionMakers),len(self.game.feasibles)))
        for idx,dm in enumerate(self.game.decisionMakers):
            for state in range(len(self.game.feasibles.decimal)):
                nashStabilities[idx,state]= self.nash(dm,state)[0]

        numpy.invert(nashStabilities.astype('bool'),nashStabilities)
        self.nashEquilibria = numpy.invert(sum(nashStabilities,0).astype('bool'))


            #SEQ calculation
        seqStabilities = numpy.zeros((len(self.game.decisionMakers),len(self.game.feasibles)))
        for idx,dm in enumerate(self.game.decisionMakers):
            for state in range(len(self.game.feasibles.decimal)):
                seqStabilities[idx,state]= self.seq(dm,state)[0]

        numpy.invert(seqStabilities.astype('bool'),seqStabilities)
        self.seqEquilibria = numpy.invert(sum(seqStabilities,0).astype('bool'))


            #SIM calculation
        simStabilities = numpy.zeros((len(self.game.decisionMakers),len(self.game.feasibles)))
        for idx,dm in enumerate(self.game.decisionMakers):
            for state in range(len(self.game.feasibles.decimal)):
                simStabilities[idx,state] = self.sim(dm,state)[0]

        numpy.invert(simStabilities.astype('bool'),simStabilities)
        self.simEquilibria = numpy.invert(sum(simStabilities,0).astype('bool'))

            #SEQ + SIM calculation
        seqSimStabilities = numpy.bitwise_and(simStabilities.astype('bool'), seqStabilities.astype('bool'))
        self.seqSimEquilibria = numpy.invert(sum(seqSimStabilities,0).astype('bool'))

            #GMR calculation
        gmrStabilities = numpy.zeros((len(self.game.decisionMakers),len(self.game.feasibles)))
        for idx,dm in enumerate(self.game.decisionMakers):
            for state in range(len(self.game.feasibles.decimal)):
                gmrStabilities[idx,state]=self.gmr(dm,state)[0]

        numpy.invert(gmrStabilities.astype('bool'),gmrStabilities)
        self.gmrEquilibria = numpy.invert(sum(gmrStabilities,0).astype('bool'))


            #SMR calculations
        smrStabilities = numpy.zeros((len(self.game.decisionMakers),len(self.game.feasibles)))
        for idx,dm in enumerate(self.game.decisionMakers):
            for state in range(len(self.game.feasibles.decimal)):
                smrStabilities[idx,state]=self.smr(dm,state)[0]

        numpy.invert(smrStabilities.astype('bool'),smrStabilities)
        self.smrEquilibria = numpy.invert(sum(smrStabilities,0).astype('bool'))

        self.allEquilibria = numpy.vstack((self.nashEquilibria,
                                        self.gmrEquilibria,
                                        self.seqEquilibria,
                                        self.simEquilibria,
                                        self.seqSimEquilibria,
                                        self.smrEquilibria))
        print("calculations complete.")


class InverseSolver(RMGenerator):
    def __init__(self,game):
        RMGenerator.__init__(self,game)

        self.desEq = self.game.desEq
        self.vary  = self.game.vary

    def _decPerm(self,full,vary):
        """Returns all possible permutations of a list 'full' when only the span
        defined by 'vary' is allowed to change. (UI vector for 1 DM)."""
        if not vary:
            yield full
        else:
            for x in itertools.permutations(full[vary[0]:vary[1]]):
                yield full[:vary[0]]+list(x)+full[vary[1]:]

    def prefPermGen(self,pref,vary):
        """Returns all possible permutations of the group of preference vectors
        'pref' when the spans defined in 'vary' are allowed to move for each DM."""
        b=[self._decPerm(y,vary[x]) for x,y in enumerate(pref)]
        c=itertools.product(*b)
        for y in c:
            yield y
            
    def nashCond(self):
        """Generates a list of the conditions that preferences must satisfy for Nash stability to exist."""
        output=[""]
        for dm in range(len(self.game.decisionMakers)):
            desEq = self.game.feasibles.toOrdered[self.desEq[0]]
            mblNash = [self.game.feasibles.toOrdered[state] for state in self.mustBeLowerNash[0][dm]]
            message = "For DM %s: %s must be more preferred than %s"%(dm,desEq,mblNash)
            output.append(message)
        return "\n\n".join(output)
        
    def gmrCond(self):
        """Generates a list of the conditions that preferences must satisfy for GMR stability to exist."""
        output=[""]
        for dm in range(len(self.game.decisionMakers)):
            desEq = self.game.feasibles.toOrdered[self.desEq[0]]
            mblGMR = [self.game.feasibles.toOrdered[state] for state in self.mustBeLowerNash[0][dm]]
            mbl2GMR = []
            for stateList in self.mustBeLowerGMR[0][dm]:
                mbl2GMR.extend(stateList)
            mbl2GMR = list(set(mbl2GMR))
            mbl2GMR = [self.game.feasibles.toOrdered[state] for state in mbl2GMR] 
            message = "For DM %s: %s must be more preferred than %s"%(dm,desEq,mblGMR)
            message += "\n\n    or at least one of %s must be less preferred than %s"%(mbl2GMR,desEq)
            output.append(message)
        return "\n\n".join(output)
        
    def seqCond(self):
        """Generates a list of the conditions that preferences must satisfy for SEQ stability to exist."""
        output=[""]
        for dm in range(len(self.game.decisionMakers)):
            desEq = self.game.feasibles.toOrdered[self.desEq[0]]
            mblSEQ = [self.game.feasibles.toOrdered[state] for state in self.mustBeLowerNash[0][dm]]
            message = "For DM %s: %s must be more preferred than %s"%(dm,desEq,mblSEQ)
            for dm2 in range(len(self.game.decisionMakers)):
                if dm2 == dm:
                    continue
                for state1 in self.mustBeLowerNash[0][dm]:
                    for state2 in self.reachable(dm2,state1):
                        s1 = self.game.feasibles.toOrdered[state1]
                        s2 = self.game.feasibles.toOrdered[state2]
                        message += "\n\n    or if %s is preferred to %s for DM %s, %s must be less preferred than %s for DM %s"%(s2,s1,dm2,s2,desEq,dm)
            output.append(message)
        return "\n\n".join(output)
        

    def _mblInit(self):
        """Used internally to initialize the 'Must Be Lower' arrays used in inverse calculation."""
        self.mustBeLowerNash = [[self.reachable(dm,state) for dm in range(len(self.game.decisionMakers))] for state in self.desEq]
        #mustBeLowerNash[state0][dm] contains the states that must be less preferred than 'state0' for 'dm'
        # to have a Nash equilibrium at 'state0'.

        self.mustBeLowerGMR = [[[[] for state1 in dm] for dm in state] for state in self.mustBeLowerNash]
        #mustBeLowerGMR[state0][dm][idx] contains the states that 'dm' could be sanctioned to after taking
        # the move in 'idx' from 'state0'. If, for each 'idx' there is at least one state less preferred
        # than 'state0', then 'state0' is GMR.  Sanctions are UMs for opponents, but not necessarily UIs.

        for x,state0 in enumerate(self.mustBeLowerNash):
            for y,dm in enumerate(state0):      #'dm' contains a list of reachable states for dm from 'state0'
                for z,state1 in enumerate(dm):
                    for dm2 in range(len(self.game.decisionMakers)):
                        if y != dm2:
                            self.mustBeLowerGMR[x][y][z]+= self.reachable(dm2,state1)

        #seq check uses same 'mustBeLower' as GMR, as sanctions are dependent on the UIs available to
        # opponents, and as such cannot be known until the preference vectors are set.

        self.mustBeLowerSMR = [[[[[] for idx in state1] for state1 in dm] for dm in state0] for state0 in self.mustBeLowerGMR]
        #mustBeLowerSMR[state0][dm][idx][idx2] contains the states that 'dm' could countermove to
        # if sanction 'idx2' was taken by opponents after 'dm' took move 'idx' from 'state0'.
        # if at least one state is more preferred that 'state0' for each 'idx2', then the state is
        # not SMR for 'dm'.

        for x,state0 in enumerate(self.mustBeLowerGMR):
            for y,dm in enumerate(state0):
                for z,idx in enumerate(dm): #idx contains a list of
                    self.mustBeLowerSMR[x][y][z] = [self.reachable(y,state2) for state2 in idx]


    def findEquilibria(self):
        """Generates a list of all requested preference vectors, then checks if they meet equilibrium requirements."""
        self._mblInit()
        self.pVecs = list(self.prefPermGen(self.game.prefVec,self.vary))
        self.pVecsOrd = list(self.prefPermGen(self.game.prefVecOrd,self.vary))
        self.nash  = numpy.ones((len(self.pVecs),len(self.game.decisionMakers))).astype('bool')
        self.gmr   = numpy.zeros((len(self.pVecs),len(self.game.decisionMakers))).astype('bool')
        self.seq   = numpy.zeros((len(self.pVecs),len(self.game.decisionMakers))).astype('bool')
        self.smr   = numpy.zeros((len(self.pVecs),len(self.game.decisionMakers))).astype('bool')

        for prefsI,prefsX in enumerate(self.pVecs):
            payoffs =[[0]*(2**len(self.game.options)) for x in range(len(self.game.decisionMakers))]

            for dm in range(len(self.game.decisionMakers)):
                for i,y in enumerate(prefsX[dm]):
                    try:
                        for z in y:
                            payoffs[dm][z] = len(self.game.feasibles) - i
                    except TypeError:
                        payoffs[dm][y] = len(self.game.feasibles) - i
            #check if Nash
            for dm in range(len(self.game.decisionMakers)):
                for state0p,state0d in enumerate(self.desEq):
                    if not self.nash[prefsI,dm]: break
                    pay0=payoffs[dm][state0d]        #payoff of the original state; higher is better
                    for pay1 in (payoffs[dm][state1] for state1 in self.mustBeLowerNash[state0p][dm]):    #get preferences of all states reachable by 'dm'
                        if pay0<pay1:       #prefs0>prefs1 means a UI exists
                            self.nash[prefsI,dm]=False
                            break

            #check if GMR
            self.gmr[prefsI,:]=self.nash[prefsI,:]

            for dm in range(len(self.game.decisionMakers)):
                if self.nash[prefsI,dm]:
                    continue
                for state0p,state0d in enumerate(self.desEq):
                    pay0=payoffs[dm][state0d]
                    for state1p,state1d in enumerate(self.mustBeLowerNash[state0p][dm]):
                        pay1 = payoffs[dm][state1d]
                        if pay0<pay1:   #if there is a UI available
                            #nash=False
                            self.gmr[prefsI,dm]=False
                            #print('%s is unstable by Nash, set dm %s gmr unstable'%(state0d,dm))
                            for pay2 in (payoffs[dm][state2] for state2 in self.mustBeLowerGMR[state0p][dm][state1p]):
                                if pay0>pay2:       #if initial state was preferred to sanctioned state
                                    self.gmr[prefsI,dm]=True
                                    break

            #check if SEQ
            mustBeLowerSEQ = [[[[] for state1 in dm] for dm in state] for state in self.mustBeLowerNash]

            for x,state0 in enumerate(self.mustBeLowerNash):
                for y,dm in enumerate(state0):
                    for z,state1 in enumerate(dm):
                        for dm2 in range(len(self.game.decisionMakers)):
                            if y != dm2:
                                mustBeLowerSEQ[x][y][z]+=[state2 for state2 in self.reachable(dm2,state1) if payoffs[dm2][state2]>payoffs[dm2][state1]]

            self.seq[prefsI,:]=self.nash[prefsI,:]

            for dm in range(len(self.game.decisionMakers)):
                if self.nash[prefsI,dm]:
                    continue
                for state0p,state0d in enumerate(self.desEq):
                    pay0=payoffs[dm][state0d]
                    for state1p,state1d in enumerate(self.mustBeLowerNash[state0p][dm]):
                        pay1 = payoffs[dm][state1d]
                        if pay0<pay1:  #if there is a UI available
                            #nash=False
                            self.seq[prefsI,dm]=False
                            #print('%s is unstable by Nash, set dm %s gmr unstable'%(state0d,dm))
                            for pay2 in (payoffs[dm][state2] for state2 in mustBeLowerSEQ[state0p][dm][state1p]):
                                if pay0>pay2:       #if initial state was preferred to sanctioned state
                                    self.seq[prefsI,dm]=True        #set to true since sanctioned, however this will be broken if another UI exists.
                                    break

            #check if SMR
            self.smr[prefsI,:]=self.nash[prefsI,:]

            for dm in range(len(self.game.decisionMakers)):
                if self.nash[prefsI,dm]:
                    continue
                for state0p,state0d in enumerate(self.desEq):
                    pay0=payoffs[dm][state0d]
                    for state1p,state1d in enumerate(self.mustBeLowerNash[state0p][dm]):
                        pay1 = payoffs[dm][state1d]
                        if pay0<pay1:   #if there is a UI available
                            #nash=False
                            self.smr[prefsI,dm]=False
                            for state2p,state2d in enumerate(self.mustBeLowerGMR[state0p][dm][state1p]):
                                pay2 = payoffs[dm][state2d]
                                if pay0>pay2:       #if initial state was preferred to sanctioned state
                                    self.smr[prefsI,dm]=True        #set to true since sanctioned, however this will be broken if another UI exists, or if dm can countermove.
                                    for pay3 in (payoffs[dm][state3] for state3 in self.mustBeLowerSMR[state0p][dm][state1p][state2p]):
                                        if pay0<pay3:       #if countermove is better than original state.
                                            self.smr[prefsI,dm]=False
                                            break
                                    break       #check this

        self.equilibriums = numpy.vstack((self.nash.all(axis=1),self.seq.all(axis=1),self.gmr.all(axis=1),self.smr.all(axis=1)))

    def filter(self,filt):
        values = []
        for pVeci,pVecOrd in enumerate(self.pVecsOrd):
            eqms = self.equilibriums[:,pVeci]
            if numpy.greater_equal(eqms,filt).all():
                values.append(tuple(list(pVecOrd)+[bool(x) for x in eqms]))
        counts = self.equilibriums.sum(axis=1)
        return values,counts


class MatrixCalc(RMGenerator):
    def __init__(self,game):
        RMGenerator.__init__(game)






def main():
    from data_01_conflictModel import ConflictModel
    g1 = ConflictModel('Prisoners.gmcr')

    rms = LogicalSolver(g1)


if __name__ == '__main__':
    main()
