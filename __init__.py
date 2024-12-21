#-----------------------------------------------------------
# Copyright (C) 2023 Ben Wirf
# ben.wirf@gmail.com
#-----------------------------------------------------------
# Licensed under the terms of GNU GPL 2
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#---------------------------------------------------------------------
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (QAction, QDialog, QLabel, QLineEdit, QComboBox,
                            QRadioButton, QHBoxLayout, QVBoxLayout, QPushButton)
                            
from qgis.PyQt.QtGui import QFont, QColor, QIcon

from qgis.core import (Qgis, QgsProject, QgsDistanceArea, QgsCoordinateTransform,
                        QgsGeometry, QgsPoint, QgsCircle)

from qgis.gui import (QgsMapTool, QgsRubberBand, QgsVertexMarker,
                        QgsGeometryRubberBand, QgsSnapIndicator)

import os

def classFactory(iface):
    return MeasureRadius(iface)


class MeasureRadius:
    def __init__(self, iface):
        self.iface = iface
        self.canvas = self.iface.mapCanvas()
        self.map_tool = MeasureRadiusTool(self.canvas)

    def initGui(self):
        self.tool_bar = self.iface.attributesToolBar()
        self.folder_name = os.path.dirname(os.path.abspath(__file__))
        self.icon_path = os.path.join(self.folder_name, 'measure-radius-icon.png')
        self.action = QAction(QIcon(self.icon_path),
                                'Measure Radius',
                                self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        self.tool_bar.addAction(self.action)

    def unload(self):
        self.tool_bar.removeAction(self.action)
        del self.action

    def run(self):
        self.canvas.setMapTool(self.map_tool)
        self.map_tool.dlg.show()

class MeasureRadiusDialog(QDialog):
    
    def __init__(self):
        super(MeasureRadiusDialog, self).__init__()
        self.setGeometry( 100, 100, 550, 200)
        self.setWindowTitle('Measure')
        
        self.radius_combo_items = ['meters', 'kilometers', 'feet', 'nautical miles',
                'yards', 'miles', 'degrees', 'centimeters', 'millimeters']
        
        self.x_label = QLabel('Centre X', self)
        self.x_edit = QLineEdit(self)
        self.y_label = QLabel('Centre Y', self)
        self.y_edit = QLineEdit(self)
        self.x_layout = QHBoxLayout()
        self.x_layout.addWidget(self.x_label)
        self.x_layout.addWidget(self.x_edit)
        self.y_layout = QHBoxLayout()
        self.y_layout.addWidget(self.y_label)
        self.y_layout.addWidget(self.y_edit)
        
        self.radius_label = QLabel('Radius', self)
        self.radius_edit = QLineEdit(self)
        self.radius_combo = QComboBox(self)
        self.radius_combo.setMinimumWidth(200)
        self.radius_combo.addItems(self.radius_combo_items)
        self.radius_layout = QHBoxLayout()
        self.radius_layout.addWidget(self.radius_label)
        self.radius_layout.addWidget(self.radius_edit)
        self.radius_layout.addWidget(self.radius_combo)
        
        self.cartesian_rb = QRadioButton('Cartesian', self)
        self.cartesian_rb.setChecked(True)
        self.ellipsoidal_rb = QRadioButton('Ellipsoidal', self)
        self.rb_layout = QHBoxLayout()
        self.rb_layout.addWidget(self.cartesian_rb)
        self.rb_layout.addWidget(self.ellipsoidal_rb)
        self.rb_layout.addStretch()

        self.new_button = QPushButton('New', self)
        self.close_button = QPushButton('Close', self)
        self.button_layout = QHBoxLayout()
        self.button_layout.addStretch()
        self.button_layout.addWidget(self.new_button)
        self.button_layout.addWidget(self.close_button)
        
        self.main_layout = QVBoxLayout(self)
        self.main_layout.addLayout(self.x_layout)
        self.main_layout.addLayout(self.y_layout)
        self.main_layout.addLayout(self.radius_layout)
        self.main_layout.addLayout(self.rb_layout)
        self.main_layout.addStretch()
        self.main_layout.addLayout(self.button_layout)
        
        self.edit_font = QFont('LiberationSans', 12)
        self.edit_font.setBold(True)
        
        self.x_edit.setFont(self.edit_font)
        self.y_edit.setFont(self.edit_font)
        self.radius_edit.setFont(self.edit_font)
        self.radius_edit.setAlignment(Qt.AlignRight)
        
        self.close_button.clicked.connect(lambda: self.close())

class MeasureRadiusTool(QgsMapTool):
    
    def __init__(self, canvas):
        self.canvas = canvas
        QgsMapTool.__init__(self, self.canvas)
        
        self.project = QgsProject.instance()
        self.crs = self.project.crs()
        self.ellipsoid = self.crs.ellipsoidAcronym()
        self.units = self.crs.mapUnits()
        
        self.drawing = False
        
        self.line_rb = None
        self.radius_rb = None
        self.centre_point = None
        self.outer_point = None
        self.centre_point_marker = None
        self.outer_marker = None
        self.circle_rb = None
        self.buffer_rb = None
        
        self.radius_length = 0.0
        
        self.dlg = MeasureRadiusDialog()
        # self.dlg.show()
        self.reset_dlg_line_edits()
        
        self.dlg.radius_combo.currentIndexChanged.connect(self.units_changed)
        
        self.dlg.cartesian_rb.toggled.connect(self.radios_toggled)
        
        self.dlg.finished.connect(self.dialog_closed)
        self.dlg.new_button.clicked.connect(self.new_measurement)
        
        self.project.crsChanged.connect(self.crs_changed)
        
        self.distance_units = [Qgis.DistanceUnit.Meters,
                                Qgis.DistanceUnit.Kilometers,
                                Qgis.DistanceUnit.Feet,
                                Qgis.DistanceUnit.NauticalMiles,
                                Qgis.DistanceUnit.Yards,
                                Qgis.DistanceUnit.Miles,
                                Qgis.DistanceUnit.Degrees,
                                Qgis.DistanceUnit.Centimeters,
                                Qgis.DistanceUnit.Millimeters]
        
        #####################August 2024###########################
        self.snap_indicator = QgsSnapIndicator(self.canvas)
        self.snap_utils = self.canvas.snappingUtils()
        #####################August 2024###########################
        
    ######UTILS TO CALCULATE DISTANCES, AREAS, ELLIPSOIDAL, CARTESIAN ETC#######
    #########AND TRANSFORM BETWEEN CRS E.G. WHEN PROJECT CRS IS CHANGED#########
    def cartesian_length(self, length, input_units, output_units):
        if input_units == 0: # Meters
            if output_units == 0: # Meters
                result = length
            elif output_units == 1: # Kilometers
                result = length/1000
            elif output_units == 2: # Imperial feet
                result = length*3.28084
            elif output_units == 3: # Nautical miles
                result = length/1852
            elif output_units == 4: # Imperial yards
                result = length*1.09361
            elif output_units == 5: # Terrestrial miles
                result = length/1609.344
            elif output_units == 6: # Degrees
                result = length/111319.49
            elif output_units == 7: # Centimeters
                result = length*100
            elif output_units == 8: # Millimeters
                result = length*1000
        elif input_units == 1: # Kilometers
            if output_units == 0: # Meters
                result = length*1000
            elif output_units == 1: # Kilometers
                result = length
            elif output_units == 2: # Imperial feet
                result = length*3280.84
            elif output_units == 3: # Nautical miles
                result = length/1.852
            elif output_units == 4: # Imperial yards
                result = length*1093.61
            elif output_units == 5: # Terrestrial miles
                result = length/1.609
            elif output_units == 6: # Degrees
                result = length/111.31949
            elif output_units == 7: # Centimeters
                result = length*100000
            elif output_units == 8: # Millimeters
                result = length*1000000
        elif input_units == 2: # Imperial feet
            if output_units == 0: # Meters
                result = length/3.281
            elif output_units == 1: # Kilometers
                result = length/3281
            elif output_units == 2: # Imperial feet
                result = length
            elif output_units == 3: # Nautical Miles
                result = length/6076
            elif output_units == 4: # Imperial yards
                result = length/3
            elif output_units == 5: # Terrestrial miles
                result = length/5280
            elif output_units == 6: # Degrees
                result = length/365239.247
            elif output_units == 7: # Centimeters
                result = length*30.48
            elif output_units == 8: # Millimeters
                result = length*304.8
        elif input_units == 3: # Nautical miles
            if output_units == 0: # Meters
                result = length*1852
            if output_units == 1: # Kilometers
                result = length*1.852
            elif output_units == 2: # Imperial feet
                result = length*6076
            elif output_units == 3: # Nautical miles
                result = length
            elif output_units == 4: # Imperial yards
                result = length*2025.37
            elif output_units == 5: # Terrestrial miles
                result = length*1.15078
            elif output_units == 6: # Degrees
                result = length/60.108
            elif output_units == 7: # Centimeters
                result = length*185200
            elif output_units == 8: # Millimeters
                result = length*1852000
        elif input_units == 4: # Imperial yards
            if output_units == 0: # Meters
                result = length/1.094
            elif output_units == 1: # Kilometers
                result = length/1094
            elif output_units == 2: # Imperial feet
                result = length*3
            elif output_units == 3: # Nautical miles
                result = length/2025
            elif output_units == 4: # Imperial yards
                result = length
            elif output_units == 5: # Terrestrial miles
                result = length/1760
            elif output_units == 6: # Degrees
                result = length/121783.522
            elif output_units == 7: # Centimeters
                result = length*91.44
            elif output_units == 8: # Millimeters
                result = length*914.4
        elif input_units == 5: # Terrestrial miles
            if output_units == 0: # Meters
                result = length*1609.34
            elif output_units == 1: # Kilometers
                result = length*1.609
            elif output_units == 2: # Imperial feet
                result = length*5280
            elif output_units == 3: # Nautical miles
                result = length/1.151
            elif output_units == 4: # Imperial yards
                result = length*1760
            elif output_units == 5: # Terrestrial miles
                result = length
            elif output_units == 6: # Degrees
                result = length/69.171
            elif output_units == 7: # Centimeters
                result = length*160934
            elif output_units == 8: # Millimeters
                result = length*1609340
#############################################################
        elif input_units == 6: # Degrees
            if output_units == 0: # Meters
                result = length*111319.49
            elif output_units == 1: # Kilometers
                result = length*111.31949
            elif output_units == 2: # Imperial feet
                result = length*365239.24669
            elif output_units == 3: # Nautical miles
                result = length*60.11252
            elif output_units == 4: # Imperial yards
                result = length*121783.52206
            elif output_units == 5: # Terrestrial miles
                result = length*69.186
            elif output_units == 6: # Degrees
                result = length
            elif output_units == 7: # Centimeters
                result = length*11131949.0
            elif output_units == 8: # Millimeters
                result = length*111319490.0
#############################################################
        elif input_units == 7: # Centimeters
            if output_units == 0: # Meters
                result = length/100
            elif output_units == 1: # Kilometers
                result = length/100000
            elif output_units == 2: # Imperial feet
                result = length/30.48
            elif output_units == 3: # Nautical miles
                result = length/185200
            elif output_units == 4: # Imperial yards
                result = length/91.44
            elif output_units == 5: # Terrestrial miles
                result = length/160934
            elif output_units == 6: # Degrees
                result = length/11131949.0
            elif output_units == 7: # Centimeters
                result = length
            elif output_units == 8: # Millimeters
                result = length*10
        elif input_units == 8: # Millimeters
            if output_units == 0: # Meters
                result = length/1000
            elif output_units == 1: # Kilometers
                result = length/1000000
            elif output_units == 2: # Imperial feet
                result = length/305
            elif output_units == 3: # Nautical miles
                result = length/1852000
            elif output_units == 4: # Imperial yards
                result = length/914
            elif output_units == 5: # Terrestrial miles
                result = length/1609000
            elif output_units == 6: # Degrees
                result = length/111319490.0
            elif output_units == 7: # Centimeters
                result = length/10
            elif output_units == 8: # Millimeters
                result = length
                
        return result
    ############################################################################
    def ellipsoidal_length(self, pt1, pt2):
        da = QgsDistanceArea()
        da.setSourceCrs(self.crs, self.project.transformContext())
        da.setEllipsoid(self.ellipsoid)
        # print(pt1)
        # print(pt2)
        length = da.measureLine(pt1, pt2)
        # print(round(length, 2))
        converted_length = da.convertLengthMeasurement(length, self.distance_units[self.dlg.radius_combo.currentIndex()])
        return converted_length
            
    def transformed_geom(self, g, src_crs, dest_crs):
        x_form = QgsCoordinateTransform(src_crs, dest_crs, self.project)
        transformed_g = QgsGeometry(g)
        transformed_g.transform(x_form)
        return transformed_g
        
    def radios_toggled(self):
        if not self.centre_point or not self.outer_point:
            return
        if self.dlg.cartesian_rb.isChecked():
            current_length = self.radius_length
            converted_length = self.cartesian_length(current_length, self.units, self.dlg.radius_combo.currentIndex())
        elif self.dlg.ellipsoidal_rb.isChecked():
            converted_length = self.ellipsoidal_length(self.centre_point, self.outer_point)
        self.dlg.radius_edit.setText(str(round(converted_length, 5)))
        
    def units_changed(self, idx):
        if not self.centre_point or not self.outer_point:
            return
        if self.dlg.cartesian_rb.isChecked():
            current_length = self.radius_length
            converted_length = self.cartesian_length(current_length, self.units, idx)
        elif self.dlg.ellipsoidal_rb.isChecked():
            converted_length = self.ellipsoidal_length(self.centre_point, self.outer_point)
        self.dlg.radius_edit.setText(str(round(converted_length, 5)))

    def crs_changed(self):
        # Transform and redraw any canvas rubber bands
        if self.line_rb:
            old_line_rb_geom = self.line_rb.asGeometry()
            new_line_rb_geom = self.transformed_geom(old_line_rb_geom, self.crs, self.project.crs())
            self.line_rb.setToGeometry(new_line_rb_geom)
        if self.radius_rb:
            old_radius_rb_geom = self.radius_rb.asGeometry()
            new_radius_rb_geom = self.transformed_geom(old_radius_rb_geom, self.crs, self.project.crs())
            self.radius_rb.setToGeometry(new_radius_rb_geom)
            # Reset radius_length class attribute
            self.radius_length = new_radius_rb_geom.length()
        if self.circle_rb:
            old_circle_rb_geom = self.circle_rb.asGeometry()
            new_circle_rb_geom = self.transformed_geom(old_circle_rb_geom, self.crs, self.project.crs())
            self.circle_rb.setToGeometry(new_circle_rb_geom)
        if self.buffer_rb:
            old_buffer_rb_geom = self.buffer_rb.asGeometry()
            new_buffer_rb_geom = self.transformed_geom(old_buffer_rb_geom, self.crs, self.project.crs())
            self.buffer_rb.setToGeometry(new_buffer_rb_geom)
            
        if self.centre_point:
            self.centre_point = self.transformed_geom(QgsGeometry.fromPointXY(self.centre_point), self.crs, self.project.crs()).asPoint()
            if self.project.crs().isGeographic():
                rounding_val = 5
            else:
                rounding_val = 3
            self.dlg.x_edit.setText(str(round(self.centre_point.x(), rounding_val)))
            self.dlg.y_edit.setText(str(round(self.centre_point.y(), rounding_val)))
        if self.outer_point:
            self.outer_point = self.transformed_geom(QgsGeometry.fromPointXY(self.outer_point), self.crs, self.project.crs()).asPoint()
        if self.centre_point_marker:
            self.centre_point_marker.setCenter(self.centre_point)
        if self.outer_marker:
            self.outer_marker.setCenter(self.outer_point)
        
        self.crs = self.project.crs()
        self.ellipsoid = self.crs.ellipsoidAcronym()
        self.units = self.crs.mapUnits()
        
        ##########10-12-23######################################################
        if not self.centre_point or not self.outer_point:
            return
        if self.dlg.cartesian_rb.isChecked():
            current_length = self.radius_length
            converted_length = self.cartesian_length(current_length, self.units, self.dlg.radius_combo.currentIndex())
        elif self.dlg.ellipsoidal_rb.isChecked():
            converted_length = self.ellipsoidal_length(self.centre_point, self.outer_point)
        self.dlg.radius_edit.setText(str(round(converted_length, 5)))
        #######################################################################
                
    def dialog_closed(self, result):
        # print(result)
        self.clear_canvas_items()
        self.reset_dlg_line_edits()
                
    def new_measurement(self):
        self.clear_canvas_items()
        self.reset_dlg_line_edits()
        
    def reset_dlg_line_edits(self):
        self.dlg.x_edit.clear()
        self.dlg.y_edit.clear()
        self.dlg.radius_edit.setText(str(round(self.radius_length, 5)))
        
    def canvasPressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drawing = True
            if not self.dlg.isVisible():
                self.dlg.show()
            self.reset_dlg_line_edits()
            if self.line_rb:
                self.line_rb.reset()
                self.line_rb = None
            if self.circle_rb:
                self.canvas.scene().removeItem(self.circle_rb)
                self.circle_rb = None
            if self.centre_point_marker:
                self.canvas.scene().removeItem(self.centre_point_marker)
                self.centre_point_marker = None
                self.centre_point = None # NOV_2024
            ######TEMP BLOCK TO 'RESET' EVERYTHING ON LEFT CLICK
            if self.outer_marker:
                self.canvas.scene().removeItem(self.outer_marker)
                self.outer_marker = None
                self.outer_point = None # NOV_2024
            if self.radius_rb:
                self.canvas.scene().removeItem(self.radius_rb)
                self.radius_rb = None
            if self.buffer_rb:
                self.canvas.scene().removeItem(self.buffer_rb)
                self.buffer_rb = None
            ####################################################
            self.line_rb = QgsRubberBand(self.canvas, Qgis.GeometryType.Line)
            self.circle_rb = QgsRubberBand(self.canvas, Qgis.GeometryType.Polygon)
            
            self.centre_point_marker = QgsVertexMarker(self.canvas)
            self.centre_point_marker.setColor(QColor(222,155,67,150))
            self.centre_point_marker.setIconType(QgsGeometryRubberBand.ICON_CIRCLE)
            self.centre_point_marker.setIconSize(10)
            self.centre_point_marker.setPenWidth(1)
            self.centre_point_marker.setFillColor(QColor(222,155,67,100))
            self.centre_point = event.mapPoint()
            ####AUG 2024
            snap_match = self.snap_utils.snapToMap(event.mapPoint())
            self.snap_indicator.setMatch(snap_match)
            if self.snap_indicator.match().type():
                # cursor is snapped to a vertex/segment (based on snapping settings)
                self.centre_point = self.snap_indicator.match().point()
            ####AUG 2024
            self.centre_point_marker.setCenter(self.centre_point)
            self.centre_point_marker.show()
            if self.project.crs().isGeographic():
                rounding_val = 5
            else:
                rounding_val = 3
            self.dlg.x_edit.setText(str(round(self.centre_point.x(), rounding_val)))
            self.dlg.y_edit.setText(str(round(self.centre_point.y(), rounding_val)))
                        
        elif event.button() == Qt.RightButton:
            self.drawing = False
            if self.line_rb and self.circle_rb and self.centre_point_marker:
                self.canvas.scene().removeItem(self.line_rb)
                self.line_rb = None
                self.canvas.scene().removeItem(self.circle_rb)
                self.circle_rb = None
                
                self.outer_point = event.mapPoint()
                ####AUG 2024
                snap_match = self.snap_utils.snapToMap(event.mapPoint())
                self.snap_indicator.setMatch(snap_match)
                if self.snap_indicator.match().type():
                    # cursor is snapped to a vertex/segment (based on snapping settings)
                    self.outer_point = self.snap_indicator.match().point()
                ####AUG 2024
                # Create radius (line) and buffer (polygon) rubber bands
                self.radius_rb = QgsRubberBand(self.canvas, Qgis.GeometryType.Line)
                self.radius_rb.setColor(QColor(222,155,67,150))
                self.radius_rb.setWidth(3)
                radius_geom = self.create_radius_geom()
                self.radius_rb.setToGeometry(radius_geom)
                
                self.radius_length = radius_geom.length()
                
                self.buffer_rb = QgsRubberBand(self.canvas, Qgis.GeometryType.Polygon)
                self.buffer_rb.setStrokeColor(QColor(25,25,25))
                self.buffer_rb.setWidth(2)
                self.buffer_rb.setFillColor(QColor(125,125,125,35))
                buffer_geom = self.create_buffer_geom()
                self.buffer_rb.setToGeometry(buffer_geom)
                
                self.outer_marker = QgsVertexMarker(self.canvas)
                self.outer_marker.setColor(QColor(222,155,67,150))
                self.outer_marker.setIconType(QgsGeometryRubberBand.ICON_CIRCLE)
                self.outer_marker.setIconSize(10)
                self.outer_marker.setPenWidth(1)
                self.outer_marker.setFillColor(QColor(222,155,67,100))
                self.outer_marker.setCenter(self.outer_point)
                
                # Show rubber bands and markers
                self.buffer_rb.show()
                self.radius_rb.show()
                self.outer_marker.show()
                
    def create_radius_geom(self):
        radius_geom = QgsGeometry.fromPolyline([QgsPoint(self.centre_point), QgsPoint(self.outer_point)])
        return radius_geom

    def create_buffer_geom(self):
        #buffer_geom = QgsGeometry.fromPointXY(self.centre_point).buffer(self.create_radius_geom().length(), 250)
        ###
        tmp_ctr_pt = QgsPoint(self.centre_point)
        tmp_out_pt = QgsPoint(self.outer_point)
        buffer_dist = self.create_radius_geom().length()
        az = tmp_ctr_pt.azimuth(tmp_out_pt)
        circ = QgsCircle(tmp_ctr_pt, buffer_dist, az)
        poly = circ.toPolygon(360)
        poly_geom = QgsGeometry(poly)
        buffer_geom = poly_geom.densifyByCount(10)
        ###
        return buffer_geom
        
    def canvasMoveEvent(self, event):
        cursor_point = event.mapPoint()
        ####AUG 2024
        snap_match = self.snap_utils.snapToMap(cursor_point)
        self.snap_indicator.setMatch(snap_match)
        if self.snap_indicator.match().type():
            # cursor is snapped to a vertex/segment (based on snapping settings)
            cursor_point = self.snap_indicator.match().point()
        ####AUG 2024
        if not self.drawing:
            return
        self.outer_point = cursor_point
        if self.line_rb:
            self.line_rb.reset()
            self.line_rb.setColor(QColor(222,155,67,150))
            self.line_rb.setWidth(3)
            line_geom = self.create_radius_geom()
            self.line_rb.setToGeometry(line_geom)
            self.line_rb.show()
            
        if self.circle_rb:
            self.circle_rb.reset()
            self.circle_rb.setStrokeColor(QColor(25,25,25))
            self.circle_rb.setWidth(2)
            self.circle_rb.setFillColor(QColor(125,125,125,35))
            circle_geom = self.create_buffer_geom()
            self.circle_rb.setToGeometry(circle_geom)
            self.circle_rb.show()
            
            canvas_units = self.units
            dest_units = self.dlg.radius_combo.currentIndex()
            self.radius_length = line_geom.length()
            if self.dlg.cartesian_rb.isChecked():
                display_length = self.cartesian_length(self.radius_length, canvas_units, dest_units)
            elif self.dlg.ellipsoidal_rb.isChecked():
                display_length = self.ellipsoidal_length(self.centre_point, cursor_point)
            self.dlg.radius_edit.setText(str(round(display_length, 5)))
            
    def clear_canvas_items(self):
        self.drawing = False
        self.radius_length = 0.0
        if self.centre_point_marker:
            self.canvas.scene().removeItem(self.centre_point_marker)
            self.centre_point_marker = None
            self.centre_point = None # NOV_2024
        if self.line_rb:
            self.canvas.scene().removeItem(self.line_rb)
            self.line_rb = None
        if self.outer_marker:
            self.canvas.scene().removeItem(self.outer_marker)
            self.outer_marker = None
            self.outer_point = None # NOV_2024
        if self.radius_rb:
            self.canvas.scene().removeItem(self.radius_rb)
            self.radius_rb = None
        if self.circle_rb:
            self.canvas.scene().removeItem(self.circle_rb)
            self.circle_rb = None
        if self.buffer_rb:
            self.canvas.scene().removeItem(self.buffer_rb)
            self.buffer_rb = None
    
    def deactivate(self):
        self.clear_canvas_items()
        self.dlg.close()