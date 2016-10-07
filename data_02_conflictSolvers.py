# Copyright:   (c) Oskar Petersons 2013

"""Conflict analysis engines and reachability matrix generators."""

import numpy as np
import itertools
import json


class RMGenerator:
    """Reachability matrix class.

    When initialized with a conflict for data, it produces reachability
    matrices for each of the decision makers.

    Key methods for extracting data from the matrix are:
    reachable(dm, state)
    uis(dm, state)

    Other methods are provided that allow the reachability data to be exported.
    """

    def __init__(self, conflict, useCoalitions=True):
        """Generate reachability matrices for conflict participants."""
        self.conflict = conflict

        if useCoalitions:
            if len(self.conflict.coalitions) == 0:
                for dm in self.conflict.decisionMakers:
                    self.conflict.coalitions.append(dm)
            self.effectiveDMs = self.conflict.coalitions
        else:
            self.effectiveDMs = self.conflict.decisionMakers

        for dm in self.effectiveDMs:
            dm.calculatePreferences()
            dm.calculatePerceived()

            dm.reachability = np.zeros((len(conflict.feasibles),
                                        len(conflict.feasibles)),
                                       np.int_)
            if dm.isCoalition:
                pmTemp = np.array([dm.payoffs for dm in dm]).transpose()
                pmTemp = pmTemp[np.newaxis, :, :] - pmTemp[:, np.newaxis]
                dm.payoffMatrix = (pmTemp > 0).all(axis=2)
            else:
                pmTemp = np.array(dm.payoffs)
                dm.payoffMatrix = pmTemp[np.newaxis, :] - pmTemp[:, np.newaxis]

            # generate a flat list of move values controlled by other DMs

            otherCOsMoves = [option.dec_val for otherDM in self.effectiveDMs
                             if otherDM != dm for option in otherDM.options]
            focalCOmoves = [option.dec_val for option in dm.options]

            # translate the list of moves values for other DMs into a list of
            # base states
            fixedStates = [0]
            for val in otherCOsMoves:
                fixedStates = [y + z for y in fixedStates for z in [0, val]]

            # translate the list of focal DM move values into a list of focal
            # DM states
            manipulatedStates = [0]
            for val in focalCOmoves:
                manipulatedStates = [y + z for y in manipulatedStates
                                     for z in [0, val]]

            # find the full set of mutually reachable states (controlled by the
            # focal DM) for each fixed state (controlled by the other DMs)
            for state in fixedStates:
                reachable = [state]     # starting point
                # full reachable set
                reachable = [y + z for y in reachable
                             for z in manipulatedStates]
                # remove infeasibles
                reachable = [y for y in reachable
                             if (y in conflict.feasibles.decimal)]

                # add one set of mutually reachable states
                for state0 in reachable:
                    s0 = self.conflict.feasibles.toOrdered[state0] - 1
                    for state1 in reachable:
                        s1 = self.conflict.feasibles.toOrdered[state1] - 1
                        if s0 != s1:
                            dm.reachability[s0, s1] = 1

            # Remove irreversible states ######################################
            for option in conflict.options:
                if option.permittedDirection != "both":
                    for idx0, state0yn in enumerate(conflict.feasibles.yn):
                        # does state have potential for irreversible move?
                        # value of the irreversible move option in DMs current
                        # state (Y/N)
                        val0 = state0yn[option.master_index]
                        if (val0 == "Y") and (
                           option.permittedDirection == "fwd") or (
                           val0 == "N") and (
                           option.permittedDirection == "back"):
                            for idx1, state1yn in enumerate(
                                    conflict.feasibles.yn):
                                # is target move irreversible?
                                val1 = state1yn[option.master_index]
                                if val0 != val1:
                                    # remove irreversible moves from
                                    # reachability matrix
                                    dm.reachability[idx0, idx1] = 0

            # A DM may not move to or from a state they misperceive.
            # Remove moves to or from misperceived states
            for state in conflict.feasibles.ordered:
                if state not in dm.perceived.ordered:
                    dm.reachability[:, state - 1] = 0
                    dm.reachability[state - 1, :] = 0

    def reachable(self, dm, stateIdx):
        """List all states reachable by a decisionMaker or coalition from state.

        dm: a DecisionMaker or Coalition that was passed to the constructor.
        stateIdx: the index of the state in the conflict.
        """
        if dm not in self.effectiveDMs:
            raise ValueError("DM or Coalition not valid.")
        reachVec = np.nonzero(dm.reachability[stateIdx, :])[0].tolist()
        return reachVec

    def UIs(self, dm, stateIdx, refState=None):
        """List unilateral improvements available to dm from state.

        dm: a DecisionMaker or Coalition that was passed to the constructor.
        stateIdx is the index of the state in the conflict.
        refState (optional) is another state to be used as a baseline for
            determining whether or not a state is an improvement -- states will
            be returned as UIs only if they are reachable from stateIdx and
            more preferred from refState.
        """
        if dm not in self.effectiveDMs:

            raise ValueError("DM or Coalition not valid.")
        if refState is None:
            refState = stateIdx
        UIvec = np.nonzero(dm.reachability[stateIdx, :] *
                           dm.payoffMatrix[refState, :] > 0)[0].tolist()
        return UIvec

    def saveJSON(self, file):
        """Export conflict data to JSON format for presentation.

        Includes the full normal save file, plus reachability data and payoffs.
        """
        conflictData = self.conflict.export_rep()

        nodes = []

        for stateIdx, stateDec in enumerate(self.conflict.feasibles.decimal):
            stateYN = self.conflict.feasibles.yn[stateIdx]
            stateOrd = self.conflict.feasibles.ordered[stateIdx]
            reachable = []

            for coInd, dm in enumerate(self.effectiveDMs):
                for rchSt in self.reachable(dm, stateIdx):
                    reachable.append({'target': rchSt,
                                      'dm': 'dm{}'.format(coInd),
                                      'payoffChange': int(dm.payoffMatrix[stateIdx, rchSt])})

            nodes.append({'id': stateIdx,
                          'decimal': str(stateDec),
                          'ordered': str(stateOrd),
                          'state': str(stateYN),
                          'reachable': reachable})

        conflictData["nodes"] = nodes

        with open(file, 'w') as jsonfile:
            json.dump(conflictData, jsonfile)


class LogicalSolver(RMGenerator):
    """Solves the conflicts for equilibria.

    Uses logical definitions of stability concepts.
    """

    def __init__(self, conflict):
        """Create a logical solver."""
        RMGenerator.__init__(self, conflict)

    def chattyHelper(self, co, state):
        """Generate narration for verbose stability calculations."""
        if co.isCoalition:
            pay = [dm.payoffs[state] for dm in co.members]
        else:
            pay = co.payoffs[state]
        snippet = 'state {} (decimal {}, payoff {})'.format(
            state + 1, self.conflict.feasibles.decimal[state], pay)
        return snippet

    def checkSanctions(self, focalDM, otherDMs, state0, state1,
                       uiOnly=False, countermove=False):
        """Return (True, narration, sanctioned to) if move is sanctioned."""
        for dm in otherDMs:
            if uiOnly:
                moves = self.UIs(dm, state1)
            else:
                moves = self.reachable(dm, state1)

            # if DM has no moves, pass.
            if not moves:
                continue

            for state2 in moves:
                # check if state2 is an effective sanction
                if focalDM.payoffMatrix[state0, state2] <= 0:
                    # effective sanction found.
                    if countermove and self.checkCountermoves(focalDM, state0,
                                                              state2):
                        # countermoves allowed, and one exists.
                        print("countermoved")
                        pass
                    else:
                        narration = "a move to {0} by {1}.".format(
                            self.chattyHelper(focalDM, state2), dm.name)
                        return True, narration, state2
                # see if subsequent moves by other opponents can lead to
                # an effective sanction.
                oDMs = [d for d in otherDMs if d is not dm]
                sanc, narr, s3 = self.checkSanctions(focalDM, oDMs, state0,
                                                     state2, uiOnly,
                                                     countermove)
                if sanc:
                    narration = ("a move to state {0} by {1}, followed by "
                                 "{2}").format(state2 + 1, dm.name, narr)
                    return True, narration, s3
        return False, "no sanctions", None

    def checkCountermoves(self, dm, state0, state2):
        """Check if DM can countermove after being sanctioned to state2."""
        uis = self.UIs(dm, state2)
        print("countermoves for ", dm.name, state0, " ", state2)
        if not uis:
            return False
        print(uis)
        for state3 in uis:
            print(dm.payoffMatrix[state0, state3])
            if dm.payoffMatrix[state0, state3] > 0:
                # effective countermove found.
                return True
        return False

    def nash(self, dm, state0):
        """Calculate Nash stability.

        Returns true if state0 Nash is stable for dm.
        """
        ui = self.UIs(dm, state0)
        if not ui:
            narr = ('{0} is Nash stable for DM {1} since they have no UIs from'
                    ' this state.\n').format(self.chattyHelper(dm, state0),
                                             dm.name)
            return True, narr
        else:
            narr = ('{0} is NOT Nash stable for DM {1} since they have UIs '
                    'available to: {2}\n'
                    ).format(self.chattyHelper(dm, state0),
                             dm.name,
                             ', '.join([self.chattyHelper(dm, state1)
                                        for state1 in ui]))
            return False, narr

    def seq(self, dm, state0):
        """Calculate SEQ stability.

        Returns True if state0 is SEQ stable for dm.
        """
        ui = self.UIs(dm, state0)

        if not ui:
            narration = ("{0} is SEQ stable for DM {1} since they have no UIs "
                         "from this state.\n").format(
                self.chattyHelper(dm, state0), dm.name)
            return True, narration

        narration = ('From {0}, {1} has UIs available to: \n   {2}\nCheck '
                     'for sanctioning...\n\n'
                     ).format(self.chattyHelper(dm, state0), dm.name,
                              ',\n   '.join([self.chattyHelper(dm, state1)
                                             for state1 in ui]))
        # for each potential move...
        for state1 in ui:
            oDMs = [d for d in self.effectiveDMs if d is not dm]
            sanc, narr, s3 = self.checkSanctions(dm, oDMs, state0, state1,
                                                 uiOnly=True)
            if sanc:
                narration += ("A move to {0} is sanctioned by {1}"
                              "\n\n").format(self.chattyHelper(dm, state1),
                                             narr)
            else:
                narration += ("{0} is unstable by SEQ for focal DM {1}, "
                              "since other DMs cannot effectively sanction"
                              " a move to {2}").format(
                    self.chattyHelper(dm, state0), dm.name,
                    self.chattyHelper(dm, state1))
                return False, narration
        narration += ("{0} is stable by SEQ for focal DM {1}, since all "
                      "available UIs are sanctioned by other"
                      " players.\n\n").format(
            self.chattyHelper(dm, state0), dm.name)
        return True, narration

    def sim(self, dm, state0):
        """Calculate SIM stability.

        Returns true if state0 is SIM stable for dm.
        """
        ui = self.UIs(dm, state0)

        if not ui:
            narration = ("{0} is SIM stable since focal DM {1} has no UIs"
                         " available.\n").format(self.chattyHelper(dm, state0),
                                                 dm.name)
            return True, narration

        narration = ('From {0}, {1} has UIs available to: \n   {2}\nCheck '
                     'for sanctioning...\n\n'
                     ).format(self.chattyHelper(dm, state0), dm.name,
                              ',\n   '.join([self.chattyHelper(dm, state1)
                                             for state1 in ui]))

        dec = self.conflict.feasibles.decimal      # shorter handle
        s0dec = dec[state0]
        # find all possible UIs available to other players
        otherDMuis = [[0] + [dec[s2] - s0dec for s2 in self.UIs(oDM, state0)]
                      for oDM in self.effectiveDMs if oDM != dm]
        otherDMmovesets = itertools.product(*otherDMuis)

        for state1 in ui:
            sanctioned = False
            for moveset in otherDMmovesets:
                state2combinedDec = dec[state1] + sum(moveset)
                if state2combinedDec not in self.conflict.feasibles.decimal:
                    # move combination would lead to an infeasible state
                    # check next opponent moveset
                    continue
                state2combined = dec.index(state2combinedDec)
                if dm.payoffMatrix[state0, state2combined] <= 0:
                    narration += ("Focal DM {0}'s attempt to move to {1} is "
                                  "SIM sanctioned, due to simultaneous moves "
                                  "by other DMs leading to a final state of "
                                  "{2}.\nCheck other focal DM UIs for "
                                  "sanctioning...\n\n").format(
                                      dm.name, self.chattyHelper(dm, state1),
                                      self.chattyHelper(dm, state2combined))
                    sanctioned = True
                    break
            if sanctioned:
                # A sanction against this UI was already found. check next UI.
                continue
            # gets here if none of the opponent movesets are sanctions.
            narration += ("{0} is unstable by SIM for focal DM {1}, since no "
                          "combination of simultaneous moves by other "
                          "players can result in a sanction.\n\n").format(
                              self.chattyHelper(dm, state0), dm.name)
            return False, narration
        # gets here if all UIs were sanctioned.
        narration += ("{0} is stable by SIM for focal DM {1}, since all "
                      "available UIs are sanctioned by simultaneous moves by "
                      "other players.\n\n").format(
                          self.chattyHelper(dm, state0), dm.name)
        return True, narration

    def gmr(self, dm, state0):
        """Calculate GMR stability.

        Returns True if state0 is GMR stable for dm.
        """
        ui = self.UIs(dm, state0)

        if not ui:
            narration = ("{0} is GMR stable for DM {1} since they have no UIs "
                         "from this state.\n").format(
                self.chattyHelper(dm, state0), dm.name)
            return True, narration

        narration = ('From {0}, {1} has UIs available to: \n   {2}\nCheck '
                     'for sanctioning...\n\n'
                     ).format(self.chattyHelper(dm, state0), dm.name,
                              ',\n   '.join([self.chattyHelper(dm, state1)
                                             for state1 in ui]))
        # for each potential move...
        for state1 in ui:
            oDMs = [d for d in self.effectiveDMs if d is not dm]
            sanc, narr, s3 = self.checkSanctions(dm, oDMs, state0, state1)
            if sanc:
                narration += ("A move to {0} is sanctioned by {1}"
                              "\n\n").format(self.chattyHelper(dm, state1),
                                             narr)
            else:
                narration += ("{0} is unstable by GMR for focal DM {1}, "
                              "since other DMs cannot effectively sanction"
                              " a move to {2}").format(
                    self.chattyHelper(dm, state0), dm.name,
                    self.chattyHelper(dm, state1))
                return False, narration
        narration += ("{0} is stable by GMR for focal DM {1}, since all "
                      "available UIs are sanctioned by other"
                      " players.\n\n").format(
            self.chattyHelper(dm, state0), dm.name)
        return True, narration

    def smr(self, dm, state0):
        """Calculate SMR stability.

        Returns True if state0 is SMR stable for dm.
        """
        ui = self.UIs(dm, state0)

        if not ui:
            narration = ("{0} is SMR stable for DM {1} since they have no UIs "
                         "from this state.\n").format(
                self.chattyHelper(dm, state0), dm.name)
            return True, narration

        narration = ('From {0}, {1} has UIs available to: \n   {2}\nCheck '
                     'for sanctioning...\n\n'
                     ).format(self.chattyHelper(dm, state0), dm.name,
                              ',\n   '.join([self.chattyHelper(dm, state1)
                                             for state1 in ui]))
        # for each potential move...
        for state1 in ui:
            oDMs = [d for d in self.effectiveDMs if d is not dm]
            sanc, narr, s3 = self.checkSanctions(dm, oDMs, state0, state1,
                                                 countermove=True)
            if sanc:
                narration += ("A move to {0} is sanctioned by {1}. No "
                              "effective countermove is possible."
                              "\n\n").format(self.chattyHelper(dm, state1),
                                             narr)
            else:
                narration += ("{0} is unstable by SMR for focal DM {1}, "
                              "since other DMs cannot effectively sanction"
                              " a move to {2}").format(
                    self.chattyHelper(dm, state0), dm.name,
                    self.chattyHelper(dm, state1))
                return False, narration
        narration += ("{0} is stable by SMR for focal DM {1}, since all "
                      "available UIs are sanctioned by other"
                      " players.\n\n").format(
            self.chattyHelper(dm, state0), dm.name)
        return True, narration

    def findEquilibria(self):
        """Calculate equilibrium states for each stability concept."""
        # Nash calculation
        nashStabilities = np.zeros((len(self.effectiveDMs),
                                    len(self.conflict.feasibles)))
        for idx, dm in enumerate(self.effectiveDMs):
            for state in range(len(self.conflict.feasibles)):
                nashStabilities[idx, state] = self.nash(dm, state)[0]

        self.nashStabilities = np.copy(nashStabilities)

        np.invert(nashStabilities.astype('bool'), nashStabilities)
        self.nashEquilibria = np.invert(sum(nashStabilities, 0).astype('bool'))

        # SEQ calculation
        seqStabilities = np.zeros((len(self.effectiveDMs),
                                   len(self.conflict.feasibles)))
        for idx, dm in enumerate(self.effectiveDMs):
            for state in range(len(self.conflict.feasibles)):
                seqStabilities[idx, state] = self.seq(dm, state)[0]

        self.seqStabilities = np.copy(seqStabilities)

        np.invert(seqStabilities.astype('bool'), seqStabilities)
        self.seqEquilibria = np.invert(sum(seqStabilities, 0).astype('bool'))

        # SIM calculation
        simStabilities = np.zeros((len(self.effectiveDMs),
                                   len(self.conflict.feasibles)))
        for idx, dm in enumerate(self.effectiveDMs):
            for state in range(len(self.conflict.feasibles)):
                simStabilities[idx, state] = self.sim(dm, state)[0]

        self.simStabilities = np.copy(simStabilities)

        np.invert(simStabilities.astype('bool'), simStabilities)
        self.simEquilibria = np.invert(sum(simStabilities, 0).astype('bool'))

        # SEQ + SIM calculation
        seqSimStabilities = np.bitwise_and(simStabilities.astype('bool'),
                                           seqStabilities.astype('bool'))
        self.seqSimEquilibria = np.invert(sum(seqSimStabilities,
                                              0).astype('bool'))

        # GMR calculation
        gmrStabilities = np.zeros((len(self.effectiveDMs),
                                   len(self.conflict.feasibles)))
        for idx, dm in enumerate(self.effectiveDMs):
            for state in range(len(self.conflict.feasibles)):
                gmrStabilities[idx, state] = self.gmr(dm, state)[0]

        self.gmrStabilities = np.copy(gmrStabilities)

        np.invert(gmrStabilities.astype('bool'), gmrStabilities)
        self.gmrEquilibria = np.invert(sum(gmrStabilities, 0).astype('bool'))

        # SMR calculations
        smrStabilities = np.zeros((len(self.effectiveDMs),
                                   len(self.conflict.feasibles)))
        for idx, dm in enumerate(self.effectiveDMs):
            for state in range(len(self.conflict.feasibles)):
                smrStabilities[idx, state] = self.smr(dm, state)[0]

        self.smrStabilities = np.copy(smrStabilities)

        np.invert(smrStabilities.astype('bool'), smrStabilities)
        self.smrEquilibria = np.invert(sum(smrStabilities, 0).astype('bool'))

        # output
        self.allEquilibria = np.vstack((self.nashEquilibria,
                                        self.gmrEquilibria,
                                        self.seqEquilibria,
                                        self.simEquilibria,
                                        self.seqSimEquilibria,
                                        self.smrEquilibria))


class InverseSolver(RMGenerator):
    """Generate list of preference rankings which result in stablility."""

    def __init__(self, conflict, vary=None, desiredEquilibria=None):
        """Setup solver based on variable preferences and desired Eq states."""
        RMGenerator.__init__(self, conflict, useCoalitions=False)
        if type(desiredEquilibria) is list:
            self.desEq = desiredEquilibria[0]
        else:
            self.desEq = desiredEquilibria
        self.vary = vary
        self.conflict = conflict

        for idx, dm in enumerate(self.conflict.decisionMakers):
            dm.improvementsInv = np.sign(np.array(dm.payoffMatrix, np.float64))
            if self.vary is not None:
                varyRange = self.vary[idx]
                variedStates = []
                if varyRange != [0, 0]:
                    varyRange = dm.preferenceRanking[varyRange[0]:varyRange[1]]
                    for sl in varyRange:
                        if type(sl) is list:
                            variedStates.extend([state - 1 for state in sl])
                        else:
                            variedStates.append(sl - 1)

                for s0 in variedStates:
                    for s1 in variedStates:
                        if s0 != s1:
                            dm.improvementsInv[s0, s1] = np.nan

        # dm.improvementsInv[s0, s1] indicates whether a state s0 is more
        # preferred ( + 1), less preferred(-1), equally preferred(0), or has
        # an unspecified relation (nan) to another state s1. Generated based
        # on the vary ranges selected.

    def _decPerm(self, full, vary):
        """Return all possible permutations of a list 'full' when only the span
        defined by 'vary' is allowed to change. (UI vector for 1 DM).
        """
        if not vary:
            yield full
        else:
            for x in itertools.permutations(full[vary[0]:vary[1]]):
                yield full[:vary[0]] + list(x) + full[vary[1]:]

    def prefPermGen(self, prefRanks, vary):
        """Return all possible permutations of the group of preference rankings
        'pref' when the spans defined in 'vary' are allowed to move for each
        DM.
        """
        b = [self._decPerm(y, vary[x]) for x, y in enumerate(prefRanks)]
        c = itertools.product(*b)
        for y in c:
            yield y

    def nashCond(self):
        """Generates a list of the conditions that preferences must satisfy for
        Nash stability to exist.
        """
        output = [""]
        for dmIdx, dm in enumerate(self.conflict.decisionMakers):
            desEq = self.conflict.feasibles.ordered[self.desEq]
            mblNash = [self.conflict.feasibles.ordered[state] for state in self.mustBeLowerNash[dmIdx]]
            if len(mblNash) > 0:
                message = "For DM %s: %s must be more preferred than %s"%(dm.name, desEq, mblNash)
            else:
                message = "For DM %s: Always stable as there are no moves from %s"%(dm.name, desEq)
            output.append(message)
            if self.vary is not None:
                output.append("    With the given preference rankings and vary range:")
                message1 = ''
                for state1 in self.mustBeLowerNash[dmIdx]:
                    if np.isnan(dm.improvementsInv[self.desEq, state1]):
                        message1 += "    %s must be more preferred than %s.\n"%(desEq, self.conflict.feasibles.ordered[state1])
                    elif dm.improvementsInv[self.desEq, state1] == 1:
                        message1 = "    Equilibrium not possible as %s is always more preferred than %s"%(self.conflict.feasibles.ordered[state1], desEq)
                        break
                if message1 == '':
                    message1 = "    equilibrium exists under all selected rankings"
                output.append(message1)
        return "\n\n".join(output) + "\n\n\n\n"

    def gmrCond(self):
        """Generate a list of the conditions that preferences must satisfy for
        GMR stability to exist."""
        output = [""]
        for dmIdx, dm in enumerate(self.conflict.decisionMakers):
            desEq = self.conflict.feasibles.ordered[self.desEq]
            mblGMR = [self.conflict.feasibles.ordered[state] for state in self.mustBeLowerNash[dmIdx]]
            mbl2GMR = []
            for stateList in self.mustBeLowerGMR[dmIdx]:
                mbl2GMR.extend(stateList)
            mbl2GMR = list(set(mbl2GMR))
            mbl2GMR = [self.conflict.feasibles.ordered[state] for state in mbl2GMR]
            message = "For DM %s: %s must be more preferred than %s"%(dm.name, desEq, mblGMR)
            message += "\n\n  or at least one of %s must be less preferred than %s"%(mbl2GMR, desEq)
            output.append(message)
            if self.vary is not None:
                output.append("    With the given preference rankings and vary range:")
                message1 = ''
                for idx1, state1 in enumerate(self.mustBeLowerNash[dmIdx]):
                    if np.isnan(dm.improvementsInv[self.desEq, state1]):
                        isLower = []
                        isOpen = []
                        for state2 in self.mustBeLowerGMR[dmIdx][idx1]:
                            if np.isnan(dm.improvementsInv[self.desEq, state2]):
                                isOpen.append(state2)
                            elif dm.improvementsInv[self.desEq, state2] <= 0:
                                isLower.append(state2)
                        if isLower != []:
                            continue
                        elif isOpen != []:
                            message1 += "    at least one of [%s, %s] must be less preferred than %s\n"%(
                                self.conflict.feasibles.ordered[state1],
                                str([self.conflict.feasibles.ordered[st] for st in isOpen])[1:-1],
                                desEq)
                    elif dm.improvementsInv[self.desEq, state1] ==1:
                        isLower = []
                        isOpen = []
                        for state2 in self.mustBeLowerGMR[dmIdx][idx1]:
                            if np.isnan(dm.improvementsInv[self.desEq, state2]):
                                isOpen.append(state2)
                            elif dm.improvementsInv[self.desEq, state2] <= 0:
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
        output = [""]
        for dmIdx, dm in enumerate(self.conflict.decisionMakers):
            desEq = self.conflict.feasibles.ordered[self.desEq]
            mblSEQ = [self.conflict.feasibles.ordered[state] for state in self.mustBeLowerNash[dmIdx]]
            message = "For DM %s: %s must be more preferred than %s"%(dm.name, desEq, mblSEQ)
            for dmIdx2 in range(len(self.conflict.decisionMakers)):
                if dmIdx2 == dmIdx:
                    continue
                for state1 in self.mustBeLowerNash[dmIdx]:
                    for state2 in self.reachable(self.conflict.decisionMakers[dmIdx2], state1):
                        s1 = self.conflict.feasibles.ordered[state1]
                        s2 = self.conflict.feasibles.ordered[state2]
                        message += "\n\n  or if %s is preferred to %s for DM %s, %s must be less preferred than %s for DM %s"%(s2, s1, self.conflict.decisionMakers[dmIdx2].name, s2, desEq, dm.name)
            output.append(message)
            if self.vary is not None:
                output.append("    With the given preference rankings and vary range:")
                message1 = ''
                for idx1, state1 in enumerate(self.mustBeLowerNash[dmIdx]):
                    if np.isnan(dm.improvementsInv[self.desEq, state1]):
                        isLower1 = []
                        isOpen1 = []
                        for state2 in self.mustBeLowerGMR[dmIdx][idx1]:
                            if np.isnan(dm.improvementsInv[self.desEq, state2]):
                                isOpen1.append(state2)
                            elif dm.improvementsInv[self.desEq, state2] <= 0:
                                isLower1.append(state2)
                        if isLower1 != []:
                            continue
                        elif isOpen1 != []:
                            message2 = "    %s must be less preferred than %s\n"%(
                                self.conflict.feasibles.ordered[state1], desEq)
                            for dmIdx2 in range(len(self.conflict.decisionMakers)):
                                if dmIdx2 == dmIdx:
                                    continue
                                for state2 in self.reachable(self.conflict.decisionMakers[dmIdx2], state1):
                                    if np.isnan(self.conflict.decisionMakers[dmIdx2].improvementsInv[state1, state2]):
                                        message2 += "    OR %s must be preferred to %s by %s AND %s must be less preferred than %s by %s\n"%(
                                            self.conflict.feasibles.ordered[state2],
                                            self.conflict.feasibles.ordered[state1],
                                            self.conflict.decisionMakers[dmIdx2].name,
                                            self.conflict.feasibles.ordered[state2],
                                            desEq,
                                            self.conflict.decisionMakers[dmIdx].name)
                                    elif self.conflict.decisionMakers[dmIdx2].improvementsInv[state1, state2] == 1:
                                        message2 = ""
                            message1 += message2

                    elif dm.improvementsInv[self.desEq, state1] ==1:
                        isLower1 = []
                        isOpen1 = []
                        for state2 in self.mustBeLowerGMR[dmIdx][idx1]:
                            if np.isnan(dm.improvementsInv[self.desEq, state2]):
                                isOpen1.append(state2)
                            elif dm.improvementsInv[self.desEq, state2] <= 0:
                                isLower1.append(state2)
                        if isLower1 != []:
                            continue
                        elif isOpen1 != []:
                            message2 = "    %s must be less preferred than %s\n"%(
                                self.conflict.feasibles.ordered[state1], desEq)
                            for dmIdx2 in range(len(self.conflict.decisionMakers)):
                                if dmIdx2 == dmIdx:
                                    continue
                                for state2 in self.reachable(self.conflict.decisionMakers[dmIdx2], state1):
                                    if np.isnan(self.conflict.decisionMakers[dmIdx2].improvementsInv[state1, state2]):
                                        message2 += "    OR %s must be preferred to %s by %s AND %s must be less preferred than %s by %s\n"%(
                                            self.conflict.feasibles.ordered[state2],
                                            self.conflict.feasibles.ordered[state1],
                                            self.conflict.decisionMakers[dmIdx2].name,
                                            self.conflict.feasibles.ordered[state2],
                                            desEq,
                                            self.conflict.decisionMakers[dmIdx].name)
                                    elif self.conflict.decisionMakers[dmIdx2].improvementsInv[state1, state2] == 1:
                                        message2 = ""
                            message1 += message2
                if message1 == '':
                    message1 = "    equilibrium exists under all selected rankings"
                output.append(message1)
        return "\n\n".join(output)

    def _mblInit(self):
        """Used internally to initialize the 'Must Be Lower' arrays used in inverse calculation."""
        self.mustBeLowerNash = [self.reachable(dm, self.desEq) for dm in self.conflict.decisionMakers]
        # mustBeLowerNash[dm] contains the states that must be less preferred
        # than the desired equilibrium 'state0' for 'dm' to have a Nash
        # equilibrium at 'state0'.

        self.mustBeLowerGMR = [[[] for state1 in dm] for dm in self.mustBeLowerNash]
        # mustBeLowerGMR[dm][idx] contains the states that 'dm' could be
        # sanctioned to after taking the move in 'idx' from 'state0'. If, for
        # each 'idx' there is at least one state less preferred than 'state0',
        # then 'state0' is GMR.  Sanctions are UMs for opponents, but not
        # necessarily UIs.

        # 'dm' contains a list of reachable states for dm from 'state0'
        for y, dm in enumerate(self.mustBeLowerNash):
            for z, state1 in enumerate(dm):
                for dm2 in range(len(self.conflict.decisionMakers)):
                    if y != dm2:
                        self.mustBeLowerGMR[y][z] += self.reachable(self.conflict.decisionMakers[dm2], state1)

        # seq check uses same 'mustBeLower' as GMR, as sanctions are dependent
        # on the UIs available to opponents, and as such cannot be known until
        # the preference rankings are set.

        self.mustBeLowerSMR = [[[[] for idx in state1] for state1 in dm]
                               for dm in self.mustBeLowerGMR]
        # mustBeLowerSMR[dm][idx][idx2] contains the states that 'dm' could
        # countermove to if sanction 'idx2' was taken by opponents after 'dm'
        # took move 'idx' from 'state0'. If at least one state is more
        # preferred that 'state0' for each 'idx2', then the state is not SMR
        # for 'dm'.

        for y, dm in enumerate(self.mustBeLowerGMR):
            for z, idx in enumerate(dm):    # idx contains a list of
                self.mustBeLowerSMR[y][z] = [self.reachable(self.conflict.decisionMakers[y], state2) for state2 in idx]

    def findEquilibria(self):
        """Generate a list of all requested preference rankings, then checks if they meet equilibrium requirements."""
        self._mblInit()
        self.preferenceRankings = list(self.prefPermGen([dm.preferenceRanking for dm in self.conflict.decisionMakers], self.vary))
        self.nash = np.ones((len(self.preferenceRankings), len(self.conflict.decisionMakers))).astype('bool')
        self.gmr = np.zeros((len(self.preferenceRankings), len(self.conflict.decisionMakers))).astype('bool')
        self.seq = np.zeros((len(self.preferenceRankings), len(self.conflict.decisionMakers))).astype('bool')
        self.smr = np.zeros((len(self.preferenceRankings), len(self.conflict.decisionMakers))).astype('bool')

        for prefsIdx, prefsX in enumerate(self.preferenceRankings):
            payoffs = [[0] * len(self.conflict.feasibles) for x in range(len(self.conflict.decisionMakers))]

            for dm in range(len(self.conflict.decisionMakers)):
                for i, y in enumerate(prefsX[dm]):
                    try:
                        for z in y:
                            payoffs[dm][z - 1] = len(self.conflict.feasibles) - i
                    except TypeError:
                        payoffs[dm][y - 1] = len(self.conflict.feasibles) - i
            # check if Nash
            for dm in range(len(self.conflict.decisionMakers)):
                if not self.nash[prefsIdx, dm]:
                    break
                # payoff of the original state; higher is better
                pay0 = payoffs[dm][self.desEq]
                for pay1 in (payoffs[dm][state1] for state1 in self.mustBeLowerNash[dm]):    # get preferences of all states reachable by 'dm'
                    if pay0 < pay1:       # prefs0>prefs1 means a UI exists
                        self.nash[prefsIdx, dm] = False
                        break

            # check if GMR
            self.gmr[prefsIdx, :] = self.nash[prefsIdx, :]

            for dm in range(len(self.conflict.decisionMakers)):
                if self.nash[prefsIdx, dm]:
                    continue
                pay0 = payoffs[dm][self.desEq]
                for state1p, state1d in enumerate(self.mustBeLowerNash[dm]):
                    pay1 = payoffs[dm][state1d]
                    if pay0 < pay1:   # if there is a UI available
                        # nash=False
                        self.gmr[prefsIdx, dm] = False
                        for pay2 in (payoffs[dm][state2] for state2 in self.mustBeLowerGMR[dm][state1p]):
                            if pay0 > pay2:       # if initial state was preferred to sanctioned state
                                self.gmr[prefsIdx, dm] = True
                                break

            # check if SEQ
            mustBeLowerSEQ = [[[] for state1 in dm] for dm in self.mustBeLowerNash]

            for y, dm in enumerate(self.mustBeLowerNash):
                for z, state1 in enumerate(dm):
                    for dm2 in range(len(self.conflict.decisionMakers)):
                        if y != dm2:
                            mustBeLowerSEQ[y][z] += [state2 for state2 in self.reachable(self.conflict.decisionMakers[dm2], state1) if payoffs[dm2][state2] > payoffs[dm2][state1]]

            self.seq[prefsIdx, :] = self.nash[prefsIdx, :]

            for dm in range(len(self.conflict.decisionMakers)):
                if self.nash[prefsIdx, dm]:
                    continue
                pay0 = payoffs[dm][self.desEq]
                for state1p, state1d in enumerate(self.mustBeLowerNash[dm]):
                    pay1 = payoffs[dm][state1d]
                    if pay0 < pay1:  # if there is a UI available
                        # nash=False
                        self.seq[prefsIdx, dm] = False
                        for pay2 in (payoffs[dm][state2] for state2 in mustBeLowerSEQ[dm][state1p]):
                            if pay0 > pay2:       # if initial state was preferred to sanctioned state
                                self.seq[prefsIdx, dm] = True        # set to true since sanctioned, however this will be broken if another UI exists.
                                break

            # check if SMR
            self.smr[prefsIdx, :] = self.nash[prefsIdx, :]

            for dm in range(len(self.conflict.decisionMakers)):
                if self.nash[prefsIdx, dm]:
                    continue
                pay0 = payoffs[dm][self.desEq]
                for state1p, state1d in enumerate(self.mustBeLowerNash[dm]):
                    pay1 = payoffs[dm][state1d]
                    if pay0 < pay1:   # if there is a UI available
                        # nash=False
                        self.smr[prefsIdx, dm] = False
                        for state2p, state2d in enumerate(self.mustBeLowerGMR[dm][state1p]):
                            pay2 = payoffs[dm][state2d]
                            if pay0 > pay2:       # if initial state was preferred to sanctioned state
                                self.smr[prefsIdx, dm] = True        # set to true since sanctioned, however this will be broken if another UI exists, or if dm can countermove.
                                for pay3 in (payoffs[dm][state3] for state3 in self.mustBeLowerSMR[dm][state1p][state2p]):
                                    if pay0 < pay3:       # if countermove is better than original state.
                                        self.smr[prefsIdx, dm] = False
                                        break
                                break       # check this

        self.equilibriums = np.vstack((self.nash.all(axis=1), self.seq.all(axis=1), self.gmr.all(axis=1), self.smr.all(axis=1)))

    def filter(self, filt):
        values = []
        for pRanki, prefRank in enumerate(self.preferenceRankings):
            eqms = self.equilibriums[:, pRanki]
            if np.greater_equal(eqms, filt).all():
                values.append(tuple(list(prefRank) + ["Y" if bool(x) else "" for x in eqms]))
        counts = self.equilibriums.sum(axis=1)
        return values, counts


class GoalSeeker(RMGenerator):
    def __init__(self, conflict, goals=[]):
        RMGenerator.__init__(self, conflict)
        self.conflict = conflict
        self.goals = goals

    def validGoals(self):
        if len(self.goals) == 0:
            return False
        for g in self.goals:
            if g[0] == -1:
                return False
            if g[1] == -1:
                return False
        return True

    def nash(self):
        requirements = PatternAnd(*[self.nashGoal(s0, stable) for s0, stable in self.goals], statement="Conditions for goals using Nash:")
        conf = requirements.isImpossible()
        return requirements

    def seq(self):
        requirements = PatternAnd(*[self.seqGoal(s0, stable) for s0, stable in self.goals], statement="Conditions for goals using SEQ:")
        return requirements

    def nashGoal(self, state0, stable):
        """Generates a list of the conditions that preferences must satisfy for state0 to be stable/unstable by Nash.

        Returns a PatternAnd or a PatternOr object. """

        if stable:
            conditions = PatternAnd(statement="For %s to be stable by Nash:"%(state0 + 1))
        else:
            conditions = PatternOr(statement="For %s to be unstable by Nash:"%(state0 + 1))

        for coIdx, co in enumerate(self.effectiveDMs):
            if stable:
                conditions.append(MoreThanFor(co, state0, self.reachable(co, state0)))
            else:
                if self.reachable(co, state0):
                    conditions.append(LessThanOneOf(co, state0, self.reachable(co, state0)))

        return conditions

    def seqGoal(self, state0, stable):
        """Generate a list of the conditions that preferences must satisfy for state0 to be stable/unstable by SEQ."""
        conditions = PatternAnd(statement="For %s to be %s by SEQ:"%(state0 + 1, "stable" if stable else "unstable"))

        for coIdx, co in enumerate(self.effectiveDMs):
            if stable:
                for state1 in self.reachable(co, state0):
                    isNash = MoreThanFor(co, state0, state1)
                    isStable = PatternOr(isNash)

                    for coIdx2, co2 in enumerate(self.effectiveDMs):
                        if coIdx2 == coIdx:
                            continue
                        for state2 in self.reachable(self.effectiveDMs[coIdx2], state1):
                            isSanctioned = PatternAnd(MoreThanFor(co2, state2, state1), MoreThanFor(co, state0, state2))
                            isStable.append(isSanctioned)
                    conditions.append(isStable)
            else:
                isUnstable = PatternOr()
                for state1 in self.reachable(co, state0):
                    isUI = MoreThanFor(co, state1, state0)
                    isUnsanctionedUI = PatternAnd(isUI)
                    isUnstable.append(isUnsanctionedUI)
                    for coIdx2, co2 in enumerate(self.effectiveDMs):
                        if coIdx2 == coIdx:
                            continue
                        for state2 in self.reachable(self.effectiveDMs[coIdx2], state1):
                            notASanction = PatternOr(MoreThanFor(co2, state1, state2), MoreThanFor(co, state2, state0))
                            isUnsanctionedUI.append(notASanction)
                if len(isUnstable.plist) > 0:
                    conditions.append(isUnstable)
        return conditions


class Pattern:
    """Preference based class."""

    def __init__(self, *patterns, statement=None):
        self.plist = []
        self.co = False  # indicates that this is not a base level condition.
        self.statement = statement
        self.conf = None
        for p in patterns:
            self.append(p)

class PatternAnd(Pattern):
    """All statements must be true."""

    def append(self, p):
        if isinstance(p, PatternAnd):
            for pp in p.plist:
                self.append(pp)
        else:
            self.plist.append(p)

    def isImpossible(self, lessThans={}):
        """Check if the goal expressed by this pattern can be met.

        lessThans is a double level dict of indices [CO][State] for each CO,
        and for each state, it lists the states that must be less preferred.
        """
        for pat in self.plist:
            conf = pat.isImpossible(lessThans)
            if conf is not False:
                self.conf = conf
                return conf

    def asString(self, indent=""):
        if self.conf:
            return self.conf
        pat = [p.asString(indent + " |") for p in self.plist]
        if self.statement is not None:
            return indent + self.statement + "\n" + (indent + "AND\n").join(pat)
        else:
            return (indent + "AND\n").join(pat)


class PatternOr(Pattern):
    """At least one statement must be true."""

    def append(self, p):
        if isinstance(p, PatternOr):
            for pp in p.plist:
                self.append(pp)
        else:
            self.plist.append(p)

    def isImpossible(self, lessThans={}):
        print("!!!!! isImpossible testing doesn't work for OR statements yet.")
        for pat in self.plist:
            conf = pat.isImpossible(lessThans)
            if not conf:
                return False
        self.conf
        return conf

    def asString(self, indent=""):
        if self.conf:
            return self.conf
        patterns = [p.asString(indent + " |") for p in self.plist]
        if self.statement is not None:
            return indent + self.statement + "\n" + (indent + "OR\n").join(patterns)
        else:
            return (indent + "OR\n").join(patterns)


class MoreThanFor:
    """s0 must be more preferred than s1 for co.

    s1 can be a list.
    """

    def __init__(self, co, s0, s1):
        self.co = co
        self.s0 = s0
        if isinstance(s1, list):
            self.s1 = s1
        else:
            self.s1 = [s1]

    def isImpossible(self, lessThans):
        try:
            for s1 in self.s1:
                # true if the condition s1<s0 already exists, which conflicts with this condition.
                conflict = s1 in lessThans[self.co.name][self.s0]
                if conflict:
                    return "For Nash:\nCONFLICT, %s and %s cannot be both more preferred and less preferred than each other. Goals cannot be met. \n\n"%(self.s0 + 1, s1 + 1)
        except KeyError:
            conflict = False

        if self.co.name not in lessThans:
            lessThans[self.co.name] = {}
        for s1 in self.s1:
            if s1 not in lessThans[self.co.name]:
                lessThans[self.co.name][s1] = []
            # s1 must be less preferred than s0
            lessThans[self.co.name][s1].append(self.s0)

        return False

    def asString(self, indent=""):
        if len(self.s1) == 1:
            lp = str(self.s1[0] + 1)
        else:
            lp = "each of " + ", ".join([str(s + 1) for s in self.s1])
        return indent + "%s must be more preferred than %s for %s\n"%(self.s0 + 1, lp, self.co.name)


class LessThanOneOf:
    """s0 must be less preferred than at least one of the states in li for co."""

    def __init__(self, co, s0, li):
        self.co = co
        self.s0 = s0
        self.li = li

    def isImpossible(self, lessThans):
        return False

    def asString(self, indent=""):
        return ("{0}{1} must be less preferred than at least one of {2} "
                "for {3}\n").format(indent,
                                    self.s0 + 1,
                                    [s1 + 1 for s1 in self.li],
                                    self.co.name)


class MatrixCalc(RMGenerator):
    def __init__(self, conflict):
        RMGenerator.__init__(conflict)


def main():
    from data_01_conflictModel import ConflictModel
    g1 = ConflictModel('Prisoners.gmcr')

    rms = LogicalSolver(g1)


if __name__ == '__main__':
    main()
