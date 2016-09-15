# Copyright:   (c) Oskar Petersons 2013

"""Widget for displaying all of the feasible states left in the conflict.

Loaded by the frame_02_infeasibles module.
"""

from tkinter import Tk, StringVar, Listbox, VERTICAL, N, S, E, W
from tkinter import ttk
from data_01_conflictModel import ConflictModel

tkNSEW = (N, S, E, W)


class FeasDisp(ttk.Frame):
    """Widget for displaying all of the feasible states."""

    def __init__(self, master=None, conflict=None, *args):
        """Initialize the widget."""
        ttk.Frame.__init__(self, master, padding=5)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(2, weight=1)

        self.conflict = conflict

        self.dispFormat = StringVar(value='pattern')
        self.dispList = StringVar()
        self.feasList = []

        self.fmts = {'Pattern': 'YN-', 'List (YN)': 'YN',
                     'List (ordered and [decimal])': 'ord_dec'}
        cBoxOpts = ('Pattern', 'List (YN)', 'List (ordered and [decimal])')
        self.feasText = ttk.Label(self, text='Feasible States'
                                  ).grid(row=0, column=0, columnspan=3)
        self.cBox = ttk.Combobox(self, textvariable=self.dispFormat,
                                 values=cBoxOpts, state='readonly')
        self.cBoxLb = ttk.Label(self, text='Format:')
        self.feasLBx = Listbox(self, listvariable=self.dispList)
        self.scrl = ttk.Scrollbar(self, orient=VERTICAL,
                                  command=self.feasLBx.yview)

        # ###########
        self.cBoxLb.grid(column=0, row=1, sticky=tkNSEW, pady=3)
        self.cBox.grid(column=1, row=1, columnspan=2, sticky=tkNSEW, pady=3)
        self.feasLBx.grid(column=0, row=2, columnspan=2, sticky=tkNSEW)
        self.scrl.grid(column=2, row=2, sticky=tkNSEW)

        self.cBox.bind('<<ComboboxSelected>>', self.fmtSel)
        self.feasLBx.configure(yscrollcommand=self.scrl.set)

        self.dispFormat.set('Pattern')
        self.fmtSel()

    def fmtSel(self, *args):
        """Refresh display when a new format is selected."""
        self.refreshList()

    def setFeas(self, feasList):
        """Change the list of feasible states displayed."""
        self.feasList = feasList
        self.refreshList()

    def refreshList(self):
        """Refresh list of feasible states and display with correct format."""
        fmt = self.fmts[self.dispFormat.get()]
        if fmt == "YN-":
            feas = self.conflict.feasibles.dash
        if fmt == "YN":
            feas = self.conflict.feasibles.yn
        if fmt == "ord_dec":
            feas = self.conflict.feasibles.ordDec
        self.dispList.set(tuple(feas))


def main():
    """Run widget in test window."""
    root = Tk()
    root.columnconfigure(0, weight=1)
    root.rowconfigure(0, weight=1)

    g1 = ConflictModel('Prisoners.gmcr')

    FeasView = FeasDisp(root, g1)
    FeasView.grid(column=0, row=0, sticky=tkNSEW)

    root.mainloop()

if __name__ == '__main__':
    main()
