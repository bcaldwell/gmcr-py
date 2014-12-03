# Copyright:   (c) Oskar Petersons 2013

"""Widgets used for validating and manually entering state rankings.

Loaded by the frame_05_preferenceRanking module.
"""

from tkinter import *
from tkinter import ttk
import data_03_gmcrUtilities as gmcrUtil

class RankingEditor(ttk.Frame):
    """Displays the state ranking for a single Decision Maker and allows it to be edited."""
    def __init__(self,master,conflict,dm):
        ttk.Frame.__init__(self,master,borderwidth=2)
        
        self.master = master
        self.conflict = conflict
        self.dm = dm
        
        self.columnconfigure(1,weight=1)
        
        self.dmText = StringVar(value = dm.name + ': ')
        self.dmLabel = ttk.Label(self,textvariable=self.dmText,width=20)
        self.dmLabel.grid(row=0,column=0,sticky=(N,S,E,W))
        
        self.prefRankVar = StringVar(value=str(dm.preferenceRanking))
        self.prefRankEntry = ttk.Entry(self,textvariable=self.prefRankVar)
        self.prefRankEntry.grid(row=0,column=1,sticky=(N,S,E,W))
        
        self.errorDetails = None
        
        self.prefRankEntry.bind("<FocusOut>",self.onFocusOut)
        
    def onFocusOut(self,event):
        try:
            prefRank = eval(self.prefRankVar.get())
        except SyntaxError:
            self.errorDetails = "DM %s's preference ranking is invalid."%(self.dm.name)
            self.master.event_generate("<<errorChange>>")
            return
        except NameError:
            self.errorDetails = "DM %s's preference ranking is invalid."%(self.dm.name)
            self.master.event_generate("<<errorChange>>")
            return
        self.errorDetails = gmcrUtil.validatePreferenceRanking(prefRank,self.conflict.feasibles)
        if self.errorDetails:
            self.errorDetails += "  Check DM %s's preference ranking."%(self.dm.name)
            self.master.event_generate("<<errorChange>>")
            return
        self.dm.preferenceRanking = prefRank
        self.dm.calculatePreferences()
        self.master.event_generate("<<errorChange>>")
        
    def enableWidget(self):
        self.prefRankEntry['state'] = 'normal'
        
    def disableWidget(self):
        self.prefRankEntry['state'] = 'disabled'
        
        
class PRankEditMaster(ttk.Frame):
    """Contains a RankingEditor for each DM, plus an error box."""
        
    def __init__(self,master,conflict):
        ttk.Frame.__init__(self,master,borderwidth=2)
        
        self.conflict = conflict
        
        self.columnconfigure(0,weight=1)
        
        self.activateButton = ttk.Button(self,
                text="Press to enable manual preference ranking changes",
                command=self.enableEditing)
        self.activateButton.grid(row=0,column=0,sticky=(N,S,E,W))
        
        self.editorFrame = ttk.Frame(self)
        self.editorFrame.grid(row=2,column=0,sticky=(N,S,E,W))
        self.editorFrame.columnconfigure(0,weight=1)
        
        self.errorDisplay = Text(self,height=6)
        self.errorDisplay['state'] = 'disabled'
        self.errorDisplay.grid(row=3,column=0,sticky=(N,E,W))
        
        self.editorFrame.bind('<<errorChange>>',self.updateErrors)


    def refresh(self):
        for child in self.editorFrame.winfo_children():
            child.destroy()

        self.rankingEditors = []

        for idx,dm in enumerate(self.conflict.decisionMakers):
            newEditor = RankingEditor(self.editorFrame,self.conflict,dm)
            self.rankingEditors.append(newEditor)
            newEditor.grid(row=idx,column=0,sticky=(N,S,E,W))
        
        self.updateErrors()
        
        if not self.conflict.useManualPreferenceRanking:
            self.activateButton['text'] = "Press to enable manual preference ranking changes"
            self.activateButton['state'] = 'normal'
            for editor in self.rankingEditors:
                editor.disableWidget()
        else:
            self.activateButton['text'] = "Preference rankings entered below will be used in analysis."
            self.activateButton['state'] = 'disabled'

    def enableEditing(self):
        """Switches on manual editing of the preference rankings."""
        self.activateButton['text'] = "Preference rankings entered below will be used in analysis."
        self.activateButton['state'] = 'disabled'
        for editor in self.rankingEditors:
            editor.enableWidget()
        self.conflict.useManualPreferenceRanking = True

    def updateErrors(self,event=None):
        messages = [editor.errorDetails for editor in self.rankingEditors if editor.errorDetails]
        self.conflict.preferenceErrors = len(messages)
        

        self.errorDisplay['state'] = 'normal'
        self.errorDisplay.delete('1.0','end')
        if len(messages)>0:
            text = '\n'.join(messages)
            self.errorDisplay.insert('1.0',text)
            self.errorDisplay['foreground'] = 'red'
        else:
            self.errorDisplay.insert('1.0',"No Errors.  Preference rankings are valid.")
            self.errorDisplay['foreground'] = 'black'
            self.event_generate("<<PreferenceRankingChange>>")
        self.errorDisplay['state'] = 'disabled'

