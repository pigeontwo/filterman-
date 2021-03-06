# -*- coding: utf-8 -*-
#
# This file is part of the pyFDA project hosted at https://github.com/chipmuenk/pyfda
#
# Copyright © pyFDA Project Contributors
# Licensed under the terms of the MIT License
# (see file LICENSE in root directory for details)

"""
Widget for plotting |H(z)| in 3D
"""
from __future__ import print_function, division, unicode_literals, absolute_import
import logging
logger = logging.getLogger(__name__)

from ..compat import (QCheckBox, QWidget, QComboBox, QLabel, QLineEdit, QDial,
                      QGridLayout, QFrame, pyqtSlot, pyqtSignal)

import numpy as np
from numpy import pi, ones, sin, cos, log10
import scipy.signal as sig


import pyfda.filterbroker as fb
from pyfda.pyfda_rc import params
from pyfda.pyfda_lib import H_mag, mod_version, safe_eval
from pyfda.pyfda_qt_lib import qget_cmb_box
from pyfda.plot_widgets.mpl_widget import MplWidget

from mpl_toolkits.mplot3d.axes3d import Axes3D
from matplotlib import cm # Colormap
from matplotlib.colors import LightSource

#http://docs.enthought.com/mayavi/mayavi/mlab_running_scripts.html#running-mlab-scripts
#http://docs.enthought.com/mayavi/mayavi/auto/mlab_helper_functions.html
#http://docs.enthought.com/mayavi/mayavi/mlab.html#simple-scripting-with-mlab

if mod_version('mayavi'):
    from mayavi import mlab
    MLAB = True
else:
    MLAB = False


class Plot3D(QWidget):
    """
    Class for various 3D-plots:
    - lin / log line plot of H(f)
    - lin / log surf plot of H(z)
    - optional display of poles / zeros
    """

    # incoming, connected in sender widget (locally connected to self.process_signals() )
    sig_rx = pyqtSignal(dict)
#    sig_tx = pyqtSignal(dict) # outgoing from process_signals

    def __init__(self, parent):
        super(Plot3D, self).__init__(parent)
        self.zmin = 0
        self.zmax = 4
        self.zmin_dB = -80
        self.cmap_default = 'RdYlBu_r'
        self._construct_UI()

    def _construct_UI(self):
        self.chkLog = QCheckBox("Log.", self)
        self.chkLog.setObjectName("chkLog")
        self.chkLog.setToolTip("Logarithmic scale")
        self.chkLog.setChecked(False)

        self.chkPolar = QCheckBox("Polar", self)
        self.chkPolar.setObjectName("chkPolar")
        self.chkPolar.setToolTip("Polar coordinate range")
        self.chkPolar.setChecked(False)

        self.lblBottom = QLabel("Bottom =", self)
        self.ledBottom = QLineEdit(self)
        self.ledBottom.setObjectName("ledBottom")
        self.ledBottom.setText(str(self.zmin))
        self.ledBottom.setToolTip("Minimum display value.")

        self.lblTop = QLabel("Top:", self)
        self.ledTop = QLineEdit(self)
        self.ledTop.setObjectName("ledTop")
        self.ledTop.setText(str(self.zmax))
        self.ledTop.setToolTip("Maximum display value.")

        self.chkUC = QCheckBox("UC", self)
        self.chkUC.setObjectName("chkUC")
        self.chkUC.setToolTip("Plot unit circle")
        self.chkUC.setChecked(True)

        self.chkPZ = QCheckBox("P/Z", self)
        self.chkPZ.setObjectName("chkPZ")
        self.chkPZ.setToolTip("Plot poles and zeros")
        self.chkPZ.setChecked(True)

        self.chkHf = QCheckBox("H(f)", self)
        self.chkHf.setObjectName("chkHf")
        self.chkHf.setToolTip("Plot H(f) along the unit circle")
        self.chkHf.setChecked(True)

        modes = ['None', 'Mesh', 'Surf', 'Contour']
        self.cmbMode3D = QComboBox(self)
        self.cmbMode3D.addItems(modes)
        self.cmbMode3D.setObjectName("cmbShow3D")
        self.cmbMode3D.setToolTip("Select 3D-plot mode.")
        self.cmbMode3D.setCurrentIndex(0)
        self.cmbMode3D.setSizeAdjustPolicy(QComboBox.AdjustToContents)

        self.chkColormap_r = QCheckBox("reverse", self)
        self.chkColormap_r.setToolTip("reverse colormap")
        self.chkColormap_r.setChecked(True)

        self.cmbColormap = QComboBox(self)
        self._init_cmb_colormap()
        self.cmbColormap.setToolTip("Select colormap")

        self.chkColBar = QCheckBox("Colorbar", self)
        self.chkColBar.setObjectName("chkColBar")
        self.chkColBar.setToolTip("Show colorbar")
        self.chkColBar.setChecked(False)

        self.chkLighting = QCheckBox("Lighting", self)
        self.chkLighting.setObjectName("chkLighting")
        self.chkLighting.setToolTip("Enable light source")
        self.chkLighting.setChecked(False)

        self.lblAlpha = QLabel("Alpha", self)
        self.diaAlpha = QDial(self)
        self.diaAlpha.setRange(0., 10.)
        self.diaAlpha.setValue(10)
        self.diaAlpha.setTracking(False) # produce less events when turning
        self.diaAlpha.setFixedHeight(30)
        self.diaAlpha.setFixedWidth(30)
        self.diaAlpha.setWrapping(False)
        self.diaAlpha.setToolTip("<span>Set transparency for surf and contour plots.</span>")

        self.lblHatch = QLabel("Stride", self)
        self.diaHatch = QDial(self)
        self.diaHatch.setRange(0., 9.)
        self.diaHatch.setValue(5)
        self.diaHatch.setTracking(False) # produce less events when turning
        self.diaHatch.setFixedHeight(30)
        self.diaHatch.setFixedWidth(30)
        self.diaHatch.setWrapping(False)
        self.diaHatch.setToolTip("Set line density for various plots.")

        self.chkContour2D = QCheckBox("Contour2D", self)
        self.chkContour2D.setObjectName("chkContour2D")
        self.chkContour2D.setToolTip("Plot 2D-contours at z =0")
        self.chkContour2D.setChecked(False)

        #----------------------------------------------------------------------
        # LAYOUT for UI widgets
        #----------------------------------------------------------------------

        layGControls = QGridLayout()
        layGControls.addWidget(self.chkLog, 0, 0)
        layGControls.addWidget(self.chkPolar, 1, 0)
        layGControls.addWidget(self.lblTop, 0, 2)
        layGControls.addWidget(self.lblBottom, 1, 2)
        layGControls.addWidget(self.ledTop, 0, 4)
        layGControls.addWidget(self.ledBottom, 1, 4)
        layGControls.setColumnStretch(5,1)

        layGControls.addWidget(self.chkUC, 0, 6)
        layGControls.addWidget(self.chkHf, 1, 6)
        layGControls.addWidget(self.chkPZ, 0, 8)

        layGControls.addWidget(self.cmbMode3D, 0, 10)
        layGControls.addWidget(self.chkContour2D, 1, 10)
        layGControls.addWidget(self.cmbColormap, 0,12,1,1)
        layGControls.addWidget(self.chkColormap_r, 1,12)

        layGControls.addWidget(self.chkLighting, 0, 14)
        layGControls.addWidget(self.chkColBar, 1, 14)

        layGControls.addWidget(self.lblAlpha, 0, 15)
        layGControls.addWidget(self.diaAlpha, 0, 16)

        layGControls.addWidget(self.lblHatch, 1, 15)
        layGControls.addWidget(self.diaHatch, 1, 16)

        # This widget encompasses all control subwidgets
        self.frmControls = QFrame(self)
        self.frmControls.setObjectName("frmControls")
        self.frmControls.setLayout(layGControls)

        #----------------------------------------------------------------------
        # mplwidget
        #----------------------------------------------------------------------
        # This is the plot pane widget, encompassing the other widgets
        self.mplwidget = MplWidget(self)
        self.mplwidget.layVMainMpl.addWidget(self.frmControls)
        self.mplwidget.layVMainMpl.setContentsMargins(*params['wdg_margins'])
        self.setLayout(self.mplwidget.layVMainMpl)

        self._init_grid() # initialize grid and do initial plot

        #----------------------------------------------------------------------
        # GLOBAL SIGNALS & SLOTs
        #----------------------------------------------------------------------
        self.sig_rx.connect(self.process_signals)
        #----------------------------------------------------------------------
        # LOCAL SIGNALS & SLOTs
        #----------------------------------------------------------------------
        self.chkLog.clicked.connect(self._log_clicked)
        self.ledBottom.editingFinished.connect(self._log_clicked)
        self.ledTop.editingFinished.connect(self._log_clicked)

        self.chkPolar.clicked.connect(self._init_grid)
        self.chkUC.clicked.connect(self.draw)
        self.chkHf.clicked.connect(self.draw)
        self.chkPZ.clicked.connect(self.draw)
        self.cmbMode3D.currentIndexChanged.connect(self.draw)
        self.chkColBar.clicked.connect(self.draw)

        self.cmbColormap.currentIndexChanged.connect(self.draw)
        self.chkColormap_r.clicked.connect(self._init_cmb_colormap)

        self.chkLighting.clicked.connect(self.draw)
        self.diaAlpha.valueChanged.connect(self.draw)
        self.diaHatch.valueChanged.connect(self.draw)
        self.chkContour2D.clicked.connect(self.draw)

        self.mplwidget.mplToolbar.sig_tx.connect(self.process_signals)
        self.mplwidget.mplToolbar.enable_plot(state = False) # disable initially

#------------------------------------------------------------------------------
    @pyqtSlot(object)
    def process_signals(self, sig_dict):
        """
        Process signals coming from the navigation toolbar
        """
        if 'view_changed' in sig_dict:
            self.update_view()
        elif 'data_changed' in sig_dict or 'home' in sig_dict:
            self.draw()
        elif 'enabled' in sig_dict:
            self.enable_ui(sig_dict['enabled'])
        else:
            pass

#------------------------------------------------------------------------------
    def enable_ui(self, enabled):
        """
        Triggered when the toolbar is enabled or disabled
        """
        self.frmControls.setEnabled(enabled)
        if enabled:
            self.init_axes()
            self.draw()

#------------------------------------------------------------------------------
    def _init_cmb_colormap(self):
        """ (Re-)Load combobox with available colormaps"""
        if self.chkColormap_r.isChecked():
            cmap_list = [m for m in cm.datad if m.endswith("_r")]
        else:
            cmap_list = [m for m in cm.datad if not m.endswith("_r")]
        # *_r colormaps reverse the color order
        cmap_list.sort()
        self.cmbColormap.blockSignals(True) # don't send signal "indexChanged"
        self.cmbColormap.clear()
        self.cmbColormap.addItems(cmap_list)
        self.cmbColormap.blockSignals(False)

        idx = self.cmbColormap.findText(self.cmap_default)
        if idx == -1:
            idx = 0
        self.cmbColormap.setCurrentIndex(idx)


#------------------------------------------------------------------------------
    def _init_grid(self):
        """ Initialize (x,y,z) coordinate grid + (re)draw plot."""
        phi_UC = np.linspace(0, 2*pi, 400, endpoint=True) # angles for unit circle
        self.xy_UC = np.exp(1j * phi_UC) # x,y coordinates of unity circle

        steps = 100              # number of steps for x, y, r, phi
        #
        self.xmin = -1.5; self.xmax = 1.5  # cartesian range limits
        self.ymin = -1.5; self.ymax = 1.5

        rmin = 0;    rmax = self.xmin  # polar range limits

        # Calculate grids for 3D-Plots
        dr = rmax / steps * 2 # grid size for polar range
        dx = (self.xmax - self.xmin) / steps
        dy = (self.ymax - self.ymin) / steps # grid size cartesian range

        if self.chkPolar.isChecked(): # # Plot circular range in 3D-Plot
            [r, phi] = np.meshgrid(np.arange(rmin, rmax, dr),
                            np.linspace(0, 2 * pi, steps, endpoint=True))
            self.x = r * cos(phi)
            self.y = r * sin(phi)
        else: # cartesian grid
            [self.x, self.y] = np.meshgrid(np.arange(self.xmin, self.xmax, dx),
                                            np.arange(self.ymin, self.ymax, dy))

        self.z = self.x + 1j*self.y # create coordinate grid for complex plane

        self.draw() # initial plot

#------------------------------------------------------------------------------
    def init_axes(self):
        """
        Initialize and clear the axes to get rid of colorbar
        The azimuth / elevation / distance settings of the camera are restored
        after clearing the axes. See
        http://stackoverflow.com/questions/4575588/matplotlib-3d-plot-with-pyqt4-in-qtabwidget-mplwidget
        """

        self._save_axes()

        self.mplwidget.fig.clf() # needed to get rid of colorbar
        self.ax3d = self.mplwidget.fig.add_subplot(111, projection='3d')

        self._restore_axes()

#------------------------------------------------------------------------------
    def _save_axes(self):
        """
        Store x/y/z - limits and camera position
        """

        try:
            self.azim = self.ax3d.azim
            self.elev = self.ax3d.elev
            self.dist = self.ax3d.dist
            self.xlim = self.ax3d.get_xlim3d()
            self.ylim = self.ax3d.get_ylim3d()
            self.zlim = self.ax3d.get_zlim3d()

        except AttributeError: # not yet initialized, set standard values
            self.azim = -65
            self.elev = 30
            self.dist = 10
            self.xlim = (self.xmin, self.xmax)
            self.ylim = (self.ymin, self.ymax)
            self.zlim = (self.zmin, self.zmax)


#------------------------------------------------------------------------------
    def _restore_axes(self):
        """
        Restore x/y/z - limits and camera position
        """
        if self.mplwidget.mplToolbar.a_lk.isChecked():
            self.ax3d.set_xlim3d(self.xlim)
            self.ax3d.set_ylim3d(self.ylim)
            self.ax3d.set_zlim3d(self.zlim)
        self.ax3d.azim = self.azim
        self.ax3d.elev = self.elev
        self.ax3d.dist = self.dist


#------------------------------------------------------------------------------
    def _log_clicked(self):
        """
        Change scale and settings to log / lin when log setting is changed
        Update min / max settings when lineEdits have been edited
        """
        self.log = self.chkLog.isChecked()
        if self.sender().objectName() == 'chkLog': # clicking chkLog triggered the slot
            if self.log:
                self.ledBottom.setText(str(self.zmin_dB))
                self.zmax_dB = np.round(20 * log10(self.zmax), 2)
                self.ledTop.setText(str(self.zmax_dB))
            else:
                self.ledBottom.setText(str(self.zmin))
                self.zmax = np.round(10**(self.zmax_dB / 20), 2)
                self.ledTop.setText(str(self.zmax))
        else: # finishing a lineEdit field triggered the slot
            if self.log:
                self.zmin_dB = safe_eval(self.ledBottom.text(), self.zmin_dB, return_type='float')
                self.ledBottom.setText(str(self.zmin_dB))
                self.zmax_dB = safe_eval(self.ledTop.text(), self.zmax_dB, return_type='float')
                self.ledTop.setText(str(self.zmax_dB))
            else:
                self.zmin = safe_eval(self.ledBottom.text(), self.zmin, return_type='float')
                self.ledBottom.setText(str(self.zmin))
                self.zmax = safe_eval(self.ledTop.text(), self.zmax, return_type='float')
                self.ledTop.setText(str(self.zmax))

        self.draw()

#------------------------------------------------------------------------------
    def draw(self):
        """
        Main drawing entry point: Check whether updating is enabled in the
        toolbar and then perform the actual plot
        """
        if self.mplwidget.mplToolbar.enabled:
            self.draw_3d()

#------------------------------------------------------------------------------
    def draw_3d(self):
        """
        Draw various 3D plots
        """
        self.init_axes()

        bb = fb.fil[0]['ba'][0]
        aa = fb.fil[0]['ba'][1]

        zz = np.array(fb.fil[0]['zpk'][0])
        pp = np.array(fb.fil[0]['zpk'][1])

        wholeF = fb.fil[0]['freqSpecsRangeType'] != 'half' # not used
        f_S = fb.fil[0]['f_S']
        N_FFT = params['N_FFT']

        alpha = self.diaAlpha.value()/10.
        cmap = cm.get_cmap(str(self.cmbColormap.currentText()))
        # Number of Lines /step size for H(f) stride, mesh, contour3d:

        stride = 10 - self.diaHatch.value()
        NL = 3 * self.diaHatch.value() + 5

        surf_enabled = qget_cmb_box(self.cmbMode3D, data=False) in {'Surf', 'Contour'}
        self.cmbColormap.setEnabled(surf_enabled)
        self.chkColormap_r.setEnabled(surf_enabled)
        self.chkLighting.setEnabled(surf_enabled)
        self.chkColBar.setEnabled(surf_enabled)
        self.diaAlpha.setEnabled(surf_enabled or self.chkContour2D.isChecked())

        #cNorm  = colors.Normalize(vmin=0, vmax=values[-1])
        #scalarMap = cmx.ScalarMappable(norm=cNorm, cmap=jet)

        #-----------------------------------------------------------------------------
        # Calculate H(w) along the upper half of unity circle
        #-----------------------------------------------------------------------------


        [w, H] = sig.freqz(bb, aa, worN=N_FFT, whole=True)
        H = np.nan_to_num(H) # replace nans and inf by finite numbers

        H_abs = abs(H)
        H_max = max(H_abs)
        H_min = min(H_abs)
        #f = w / (2 * pi) * f_S                  # translate w to absolute frequencies
        #F_min = f[np.argmin(H_abs)]

        plevel_rel = 1.05 # height of plotted pole position relative to zmax
        zlevel_rel = 0.1 # height of plotted zero position relative to zmax


        if self.chkLog.isChecked(): # logarithmic scale
            bottom = np.floor(max(self.zmin_dB, 20*log10(H_min)) / 10) * 10
            top = self.zmax_dB
            top_bottom = top - bottom

            zlevel = bottom - top_bottom * zlevel_rel

            if self.cmbMode3D.currentText() == 'None': # "Poleposition" for H(f) plot only
                plevel_top = 2 * bottom - zlevel # height of displayed pole position
                plevel_btm = bottom
            else:
                plevel_top = top + top_bottom * (plevel_rel - 1)
                plevel_btm = top

        else: # linear scale
            bottom = max(self.zmin, H_min)  # min. display value
            top = self.zmax                 # max. display value
            top_bottom = top - bottom
        #   top = zmax_rel * H_max # calculate display top from max. of H(f)

            zlevel = bottom + top_bottom * zlevel_rel # height of displayed zero position

            if self.cmbMode3D.currentText() == 'None': # "Poleposition" for H(f) plot only
                #H_max = np.clip(max(H_abs), 0, self.zmax)
                # make height of displayed poles same to zeros
                plevel_top = bottom + top_bottom * zlevel_rel
                plevel_btm = bottom
            else:
                plevel_top = plevel_rel * top
                plevel_btm = top

        # calculate H(jw)| along the unity circle and |H(z)|, each clipped
        # between bottom and top
        H_UC = H_mag(bb, aa, self.xy_UC, top, H_min=bottom, log=self.chkLog.isChecked())
        Hmag = H_mag(bb, aa, self.z, top, H_min=bottom, log=self.chkLog.isChecked())


        #===============================================================
        ## plot Unit Circle (UC)
        #===============================================================
        if self.chkUC.isChecked():
        # Plot unit circle and marker at (1,0):
            self.ax3d.plot(self.xy_UC.real, self.xy_UC.imag,
                           ones(len(self.xy_UC)) * bottom, lw=2, color='k')
            self.ax3d.plot([0.97, 1.03], [0, 0], [bottom, bottom], lw=2, color='k')

        #===============================================================
        ## plot ||H(f)| along unit circle as 3D-lineplot
        #===============================================================
        if self.chkHf.isChecked():
            self.ax3d.plot(self.xy_UC.real, self.xy_UC.imag, H_UC, alpha = 0.5)
            # draw once more as dashed white line to improve visibility
            self.ax3d.plot(self.xy_UC.real, self.xy_UC.imag, H_UC, 'w--')

            if stride < 10:  # plot thin vertical line every stride points on the UC
                for k in range(len(self.xy_UC[::stride])):
                    self.ax3d.plot([self.xy_UC.real[::stride][k], self.xy_UC.real[::stride][k]],
                        [self.xy_UC.imag[::stride][k], self.xy_UC.imag[::stride][k]],
                        [np.ones(len(self.xy_UC[::stride]))[k]*bottom, H_UC[::stride][k]],
                         linewidth=1, color=(0.5, 0.5, 0.5))

        #===============================================================
        ## plot Poles and Zeros
        #===============================================================
        if self.chkPZ.isChecked():

            PN_SIZE = 8 # size of P/N symbols

            # Plot zero markers at |H(z_i)| = zlevel with "stems":
            self.ax3d.plot(zz.real, zz.imag, ones(len(zz)) * zlevel, 'o',
               markersize=PN_SIZE, markeredgecolor='blue', markeredgewidth=2.0,
                markerfacecolor='none')
            for k in range(len(zz)): # plot zero "stems"
                self.ax3d.plot([zz[k].real, zz[k].real], [zz[k].imag, zz[k].imag],
                            [bottom, zlevel], linewidth=1, color='b')

            # Plot the poles at |H(z_p)| = plevel with "stems":
            self.ax3d.plot(np.real(pp), np.imag(pp), plevel_top,
              'x', markersize=PN_SIZE, markeredgewidth=2.0, markeredgecolor='red')
            for k in range(len(pp)): # plot pole "stems"
                self.ax3d.plot([pp[k].real, pp[k].real], [pp[k].imag, pp[k].imag],
                            [plevel_btm, plevel_top], linewidth=1, color='r')

        #===============================================================
        ## 3D-Plots of |H(z)| clipped between |H(z)| = top
        #===============================================================

        m_cb = cm.ScalarMappable(cmap=cmap)  # normalized proxy object that is mappable
        m_cb.set_array(Hmag)                 # for colorbar

        #---------------------------------------------------------------
        ## 3D-mesh plot
        #---------------------------------------------------------------
        if self.cmbMode3D.currentText() == 'Mesh':
        #    fig_mlab = mlab.figure(fgcolor=(0., 0., 0.), bgcolor=(1, 1, 1))
        #    self.ax3d.set_zlim(0,2)
            self.ax3d.plot_wireframe(self.x, self.y, Hmag, rstride=5,
                    cstride=stride, linewidth=1, color='gray')

        #---------------------------------------------------------------
        ## 3D-surface plot
        #---------------------------------------------------------------
        # http://stackoverflow.com/questions/28232879/phong-shading-for-shiny-python-3d-surface-plots
        elif self.cmbMode3D.currentText() == 'Surf':
            if MLAB:
                ## Mayavi
                surf = mlab.surf(self.x, self.y, H_mag, colormap='RdYlBu', warp_scale='auto')
                # Change the visualization parameters.
                surf.actor.property.interpolation = 'phong'
                surf.actor.property.specular = 0.1
                surf.actor.property.specular_power = 5
#                s = mlab.contour_surf(self.x, self.y, Hmag, contour_z=0)
                mlab.show()


            else:
                if self.chkLighting.isChecked():
                    ls = LightSource(azdeg=0, altdeg=65) # Create light source object
                    rgb = ls.shade(Hmag, cmap=cmap) # Shade data, creating an rgb array
                    cmap_surf = None
                else:
                    rgb = None
                    cmap_surf = cmap

    #            s = self.ax3d.plot_surface(self.x, self.y, Hmag,
    #                    alpha=OPT_3D_ALPHA, rstride=1, cstride=1, cmap=cmap,
    #                    linewidth=0, antialiased=False, shade=True, facecolors = rgb)
    #            s.set_edgecolor('gray')
                s = self.ax3d.plot_surface(self.x, self.y, Hmag,
                        alpha=alpha, rstride=1, cstride=1,
                        linewidth=0, antialiased=False, facecolors=rgb, cmap=cmap_surf, shade=True)
                s.set_edgecolor(None)
        #---------------------------------------------------------------
        ## 3D-Contour plot
        #---------------------------------------------------------------
        elif self.cmbMode3D.currentText() == 'Contour':
            s = self.ax3d.contourf3D(self.x, self.y, Hmag, NL, alpha=alpha, cmap=cmap)

        #---------------------------------------------------------------
        ## 2D-Contour plot
        # TODO: 2D contour plots do not plot correctly together with 3D plots in
        #       current matplotlib 1.4.3 -> disable them for now
        # TODO: zdir = x / y delivers unexpected results -> rather plot max(H)
        #       along the other axis?
        # TODO: colormap is created depending on the zdir = 'z' contour plot
        #       -> set limits of (all) other plots manually?
        if self.chkContour2D.isChecked():
#            self.ax3d.contourf(x, y, Hmag, 20, zdir='x', offset=xmin,
#                         cmap=cmap, alpha = alpha)#, vmin = bottom)#, vmax = top, vmin = bottom)
#            self.ax3d.contourf(x, y, Hmag, 20, zdir='y', offset=ymax,
#                         cmap=cmap, alpha = alpha)#, vmin = bottom)#, vmax = top, vmin = bottom)
            s = self.ax3d.contourf(self.x, self.y, Hmag, NL, zdir='z',
                               offset=bottom - (top - bottom) * 0.05,
                                cmap=cmap, alpha=alpha)

        # plot colorbar for suitable plot modes
        if self.chkColBar.isChecked() and (self.chkContour2D.isChecked() or
                str(self.cmbMode3D.currentText()) in {'Contour', 'Surf'}):
                            self.colb = self.mplwidget.fig.colorbar(m_cb,
                                ax=self.ax3d, shrink=0.8, aspect=20,
                                pad=0.02, fraction=0.08)

        #----------------------------------------------------------------------
        ## Set view limits and labels
        #----------------------------------------------------------------------
        if not self.mplwidget.mplToolbar.a_lk.isChecked():
            self.ax3d.set_xlim3d(self.xmin, self.xmax)
            self.ax3d.set_ylim3d(self.ymin, self.ymax)
            self.ax3d.set_zlim3d(bottom, top)
        else:
            self._restore_axes()

        self.ax3d.set_xlabel('Re')#(fb.fil[0]['plt_fLabel'])
        self.ax3d.set_ylabel('Im') #(r'$ \tau_g(\mathrm{e}^{\mathrm{j} \Omega}) / T_S \; \rightarrow $')
#        self.ax3d.set_zlabel(r'$|H(z)|\; \rightarrow $')
        self.ax3d.set_title(r'3D-Plot of $|H(\mathrm{e}^{\mathrm{j} \Omega})|$ and $|H(z)|$')

        self.redraw()

#------------------------------------------------------------------------------
    def redraw(self):
        """
        Redraw the canvas when e.g. the canvas size has changed
        """
        self.mplwidget.redraw()

#------------------------------------------------------------------------------

def main():
    import sys
    from ..compat import QApplication
    app = QApplication(sys.argv)
    mainw = Plot3D(None)
    app.setActiveWindow(mainw)
    mainw.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
