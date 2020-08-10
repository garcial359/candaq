#! /usr/bin/env python3

# -*- coding: utf-8 -*-
# This DAQ program is version 7 and runs with associated gui7.py files in same folder
# Records chanel 0 on tinker board
# Needs options selection added for tinker board channels
# Form implementation generated from reading ui file 'daq_gui.ui'


from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import pyqtSignal, QMutex
from PyQt5.QtWidgets import QMessageBox, QLineEdit, QFileDialog
import subprocess
import gui71 as gui
import sys
import can
import time
import os
import piplates.TINKERplate as TINK
import time
import psutil
import csv
import datetime


class MainUiClass(QtWidgets.QMainWindow, gui.Ui_MainWindow):

    def __init__(self, parent = None):
        super(MainUiClass, self).__init__(parent)
        self.setupUi(self)
        self.recordButton.clicked.connect(self.record)
        self.abortButton.clicked.connect(self.abort)
        self.keyboardPushButton.clicked.connect(self.displayKeyboard)
        self.actionExit.triggered.connect(self.close)
        self.browserPushButton.clicked.connect(self.openFileNameDialog)

    def openFileNameDialog(self):
        options = QFileDialog.Options()
        options |= QFileDialog.DontUseNativeDialog
        fileName, _ = QFileDialog.getSaveFileName(self,"QFileDialog.getSaveFileName()","","All Files (*);;Text Files (*.txt)", options=options)
        if fileName:
            self.fileName.setText(fileName)

    def displayKeyboard(self):
        if self.checkIfProcessRunning('matchbox-keyboard'):
            #os.system("/usr/bin/toggle-keyboard.sh")
            subprocess.Popen(["killall","matchbox-keyboard"])
            self.showFullScreen()
        else:
            try:
                self.showMaximized()
                #os.system("/usr/bin/toggle-keyboard.sh")
                subprocess.Popen(["matchbox-keyboard"])
            except FileNotFoundError:
                print("keyboard Error")
                pass


    def checkIfProcessRunning(self, processName):
        for proc in psutil.process_iter():
            try:
                if processName.lower() in proc.name().lower():
                    return True
            except(psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
        return False;

    def record(self):
        if self.fileName.text() == "":
            self.updateLog("Please type in file name")
            return
        record_file_name = self.fileName.text()
        try:
            temp_file = open(record_file_name,'w')
        except:
            self.updateLog("Invalid file name or extension.\nTry harder...")
            return

        AIChecked = self.AICheckBox.isChecked()

        self.progressBar.setValue(0)
        self.recordButton.setEnabled(0)
        self.abortButton.setEnabled(1)
        self.updateLog("Recording Started...")
        self.updateLog("timestamp, count, id, dlc, Viscosity (cp), Density (gm/cc), Dielectric constant (-), Temperature (C), Status, Rp (ohms)")

        self.thread = QtCore.QThread()
        self.record_thread = recordThread(file_name = record_file_name, AICheckBox = AIChecked)
        self.record_thread.moveToThread(self.thread)
        self.thread.started.connect(self.record_thread.run)
        self.thread.finished.connect(self.record_thread.stop)
        self.record_thread.log_message.connect(self.updateLog)
        self.record_thread.log_values.connect(self.updateValues)
        self.thread.start()

        self.thread2 = QtCore.QThread()
        self.progress_thread = progressBarThread(recording_time_input = self.recordingTimeLineEdit.text())
        self.progress_thread.moveToThread(self.thread2)
        self.thread2.started.connect(self.progress_thread.run)
        self.progress_thread.timeout.connect(self.abort)
        self.progress_thread.updateProgressBar.connect(self.updateProgressBar)
        self.thread2.start()

    def abort(self):

        try:
            self.abortButton.setEnabled(0)
            self.thread.quit()
            self.thread.wait()
            self.thread2.quit()
            self.thread2.wait()
            self.abortButton.setEnabled(1)
            self.recordButton.setEnabled(1)
            self.updateLog("...Recording Ended")
        except:
            self.updateLog("Error Aborting.\nDo not click Abort button while not recording.")


    def updateProgressBar(self, progress):
        self.progressBar.setValue(progress)

    def updateLog(self, log_message):
        self.logTextEdit.append(log_message)
        
    def updateValues(self, log_values):
        # data += ("%11.6f,%10.8f,%10.8f,%10.5f,%0d,%0d" % (viscosity, density, dielectric_constant, oil_temp, status_code, Rp))
        values_list = [x.strip() for x in log_values.split(',')]
        if float(values_list[0]) != 0:
            self.visc_lineEdit.setText(values_list[0])
            self.visc_lineEdit.setCursorPosition(0)
        if float(values_list[1]) != 0:
            self.dens_lineEdit.setText(values_list[1])
            self.dens_lineEdit.setCursorPosition(0)
        if float(values_list[2]) != 0:
            self.dc_lineEdit.setText(values_list[2])
            self.dc_lineEdit.setCursorPosition(0)
        if float(values_list[3]) != 0:
            self.temp_lineEdit.setText(values_list[3])
            self.temp_lineEdit.setCursorPosition(0)
        if float(values_list[5]) != 0:
            self.rp_lineEdit.setText(values_list[5])
            self.rp_lineEdit.setCursorPosition(0)
        if self.AICheckBox.isChecked():    
            if float(values_list[6]) != 0:
                self.ai_lineEdit.setText(values_list[6])
                self.ai_lineEdit.setCursorPosition(0)          
            

class rxThread(QtCore.QObject):
    message = QtCore.pyqtSignal(can.Message)
    rx_log_message = QtCore.pyqtSignal(str)

    def __init__(self, file_name, parent = None):
        super(rxThread, self).__init__(parent)
        self.file_name = file_name.strip(".txt") + "_raw.txt"

    def run(self):
        os.system("sudo /sbin/ip link set can0 up type can bitrate 250000")
        time.sleep(0.1)
        try:
            bus = can.interface.Bus(channel='can0', bustype='socketcan_native')
        except OSError:
            self.rx_log_message.emit('Cannot find PiCAN board.')

        while MainWindow.thread.isRunning():
            try:
                recv_message = bus.recv(60)
                if recv_message != None:
                    with open(self.file_name, 'a') as f:
                        data = ','.join('%02X' % byte for byte in recv_message.data)
                        central_time = datetime.datetime.fromtimestamp(float(recv_message.timestamp)).strftime('%Y-%m-%d %H:%M:%S')
                        f.write("{},{},{},{}\n".format(recv_message.timestamp, central_time, recv_message.arbitration_id, data))
                    self.message.emit(recv_message)
                else:
                    self.rx_log_message.emit("Recieved no messages from bus")
            except can.CanError:
                self.rx_log_message.emit("canbus error")


class recordThread(QtCore.QObject):
    log_message = QtCore.pyqtSignal(str)
    log_values = QtCore.pyqtSignal(str)
    outfile = 0
    count = 0
    AIEnabled = 0
    file_name = 0


    def __init__(self, file_name, AICheckBox, parent = None):
        super(recordThread, self).__init__(parent)
        os.system("sudo /sbin/ip link set can0 down")
        self.thread = QtCore.QThread()
        self.rx_thread = rxThread(file_name = file_name)
        self.rx_thread.moveToThread(self.thread)
        self.rx_thread.message.connect(self.message_record)
        self.rx_thread.rx_log_message.connect(self.logMessage)
        self.thread.started.connect(self.rx_thread.run)
        self.file_name = file_name
        self.outfile = open(file_name,'w')
        self.AIEnabled = AICheckBox
        if AICheckBox == 1:
            print("timestamp,count,id,dlc,Viscosity (cp),Density (gm/cc),Dielectric constant (-),Temperature (C),Status,Rp (ohms),RH (%)",file = self.outfile)
        else:
            print("timestamp,count,id,dlc,Viscosity (cp),Density (gm/cc),Dielectric constant (-),Temperature (C),Status,Rp (ohms)",file = self.outfile)


    def run(self):
        if not self.thread.isRunning():
            self.thread.start()


    def message_record(self, message):
        if self.thread.isRunning():
            c = '{0:f},{1:d},{2:f},{3:x},'.format(message.timestamp, self.count, message.arbitration_id, message.dlc)
            data=''
            viscosity=0
            density=0
            dielectric_constant=0
            oil_temp=0
            Rp = 0
            status_code=0
            if message.dlc == 8:
                data_0 = '{0:x}'.format(message.data[0]).zfill(2)
                data_1 = '{0:x}'.format(message.data[1]).zfill(2)
                data_2 = '{0:x}'.format(message.data[2]).zfill(2)
                data_3 = '{0:x}'.format(message.data[3]).zfill(2)
                data_4 = '{0:x}'.format(message.data[4]).zfill(2)
                data_5 = '{0:x}'.format(message.data[5]).zfill(2)
                if message.arbitration_id == float.fromhex('1CFD083F'):
                    viscosity = int(data_1 + data_0, 16)*0.015625
                    density = int(data_3 + data_2, 16)*0.00003052
                    dielectric_constant = int(data_5 + data_4, 16)*0.00012207
                elif message.arbitration_id == float.fromhex('18FEEE3F'):
                    oil_temp = (int(data_3 + data_2, 16)*0.03125)-273.0
                elif message.arbitration_id == float.fromhex('18FF313F'):
                    status_code = int('{0:x}'.format(message.data[0]), 16)
                elif message.arbitration_id == float.fromhex('18FFFF3F'):
                    Rp = (int(data_3 + data_2 + data_1 + data_0, 16)*1000.0) + 100000              
                else:
                    self.log_message.emit("incorrect arbitration id transmitted")
            else:
                self.log_message.emit("Incorrect number of channels received")
                for i in range(message.dlc ):
                    data +=  '{0:x}'.format(message.data[i])
            
            if (self.AIEnabled == 1):
                volts = TINK.getADC(0,1)
                rh_percent = (volts - 2.0 ) / 0.08
                """
                volts = TINK.getADC(0,2)
                outstr = outstr+', '+ str(volts)
                volts = TINK.getADC(0,3)
                outstr = outstr+', '+ str(volts)
                volts = TINK.getADC(0,4)
                outstr = outstr+', '+ str(volts)
                """
            
            if (self.AIEnabled == 1):
                data += ("%11.6f,%10.8f,%10.8f,%10.5f,%0d,%0d,%6.3f" % (viscosity, density, dielectric_constant, oil_temp, status_code, Rp, rh_percent))
            else:
                data += ("%11.6f,%10.8f,%10.8f,%10.5f,%0d,%0d" % (viscosity, density, dielectric_constant, oil_temp, status_code, Rp))
            
            if status_code != 0:
                self.log_message.emit("sensor reports error code %d" % (status_code))
                
            outstr = c+data
            self.count += 1
            
            try:
                if status_code != 0 or message.arbitration_id == 486344767 or message.arbitration_id == 419360319 or message.arbitration_id == 419430207:
                    print(outstr,file = self.outfile) # Save data to file
                    self.log_message.emit(outstr)
                    self.log_values.emit(data)
            except:
                self.log_message.emit("Canbus RX Thread Error")


    def logMessage(self, log_messages):
        self.log_message.emit(log_messages)
    
    
    def format_file(self):
        time_data = []
        sensor_data = []
        RH_data = []
        formatted_data = []
        data = []
        f = open(self.file_name, 'r')
        file = csv.reader(f)
        line_count = 0
        for row in file:
            if line_count == 0:
                if (self.AIEnabled == 1):
                    data.append(["Time (min)"]+row[4:11]+["Timestamp"])
                else:
                    data.append(["Time (min)"]+row[4:10]+["Timestamp"])
            if line_count == 1:
                start_time = float(row[0])
                time = float(row[0]) - start_time
                time_data.append(time)
                if (self.AIEnabled == 1):
                    RH_data = list(map(float, row[10:11]))
                sensor_data = list(map(float, row[4:10]))
                formatted_data = sensor_data
                
            if line_count > 1:
                time = float(row[0])-start_time
                time_data.append(time)
                if (self.AIEnabled == 1):
                    RH_data = list(map(float, row[10:11]))
                sensor_data = list(map(float, row[4:11]))
                    
                time_delta = time - time_data[line_count - 2]
                central_time = datetime.datetime.fromtimestamp(float(row[0])).strftime('%Y-%m-%d %H:%M:%S')
                if time_delta < 1:
                    for index, item in enumerate(formatted_data):
                        formatted_data[index] += sensor_data[index]

                else:
                    if (self.AIEnabled == 1):
                        data.append([time_data[line_count-2]/60] + formatted_data[0:6] + [RH_data[0]] + [central_time])
                    else:
                        data.append([time_data[line_count-2]/60] + formatted_data[0:6] + [central_time])
                        
                    formatted_data = sensor_data
            line_count += 1
        
        if (self.AIEnabled == 1):
            data.append([time/60] + formatted_data[0:6] + [RH_data[0]] + [central_time])
        else:
            data.append([time/60] + formatted_data + [central_time])
        
        print("creating " + self.file_name.strip(".txt") + ".csv")
        with open(self.file_name.strip(".txt") + ".csv", 'w', newline='') as csvfile:
            csv_writer = csv.writer(csvfile, delimiter=',')
            csv_writer.writerows(data)


    def stop(self):
        self.thread.quit()
        self.thread.wait()
        self.outfile.close()
        self.format_file()
        os.system("sudo /sbin/ip link set can0 down")


class progressBarThread(QtCore.QObject):
    timeout = QtCore.pyqtSignal()
    updateProgressBar = QtCore.pyqtSignal(float)

    def __init__(self, recording_time_input, parent = None):
        super(progressBarThread, self).__init__(parent)
        self.recording_time_input = recording_time_input

    def run(self):
        progress = 0
        try:
            recording_time = 60*(int(self.recording_time_input))
        except ValueError:
            print("not a valid recording time")
            return
        while progress < 100 and MainWindow.thread.isRunning():
            QtCore.QThread.sleep(1)
            if not MainWindow.thread.isRunning():
                return
            progress += 100.0/recording_time
            self.updateProgressBar.emit(progress)
        self.timeout.emit()

    def quit(self):
        print("stop")


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    MainWindow = MainUiClass()
    MainWindow.show()
    sys.exit(app.exec())

