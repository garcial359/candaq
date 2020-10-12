#! /usr/bin/env python3

# -*- coding: utf-8 -*-
# This DAQ program is version 9 and runs with associated gui9.py files in same folder
# Records chanel 0 on tinker board
# Needs options selection added for tinker board channels
# Form implementation generated from reading ui file 'daq_gui.ui'




from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import pyqtSignal, QMutex
from PyQt5.QtWidgets import QMessageBox, QLineEdit, QFileDialog
import subprocess
import gui9 as gui
import sys
import can
import time
import os
import piplates.TINKERplate as TINK
import time
import psutil
import csv
import datetime
from struct import unpack as up


class MainUiClass(QtWidgets.QMainWindow, gui.Ui_MainWindow):

    def __init__(self, parent=None):
        super(MainUiClass, self).__init__(parent)
        self.setupUi(self)
        self.recordButton.clicked.connect(self.record)
        self.abortButton.clicked.connect(self.abort)
        self.keyboardPushButton.clicked.connect(self.displayKeyboard)
        self.actionExit.triggered.connect(self.close)
        self.browserPushButton.clicked.connect(self.openFileNameDialog)
        self.AICheckBox.hide()
        self.ai_lineEdit.hide()

    def openFileNameDialog(self):
        options = QFileDialog.Options()
        options |= QFileDialog.DontUseNativeDialog
        fileName, _ = QFileDialog.getSaveFileName(self, "QFileDialog.getSaveFileName()", "",
                                                  "All Files (*);;Text Files (*.txt)", options=options)
        if fileName:
            self.fileName.setText(fileName)

    def displayKeyboard(self):
        if self.checkIfProcessRunning('matchbox-keyboard'):
            # os.system("/usr/bin/toggle-keyboard.sh")
            subprocess.Popen(["killall", "matchbox-keyboard"])
            self.showFullScreen()
        else:
            try:
                self.showMaximized()
                # os.system("/usr/bin/toggle-keyboard.sh")
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
            temp_file = open(record_file_name, 'w')
            temp_file.close()
        except:
            self.updateLog("Invalid file name or extension.\nTry harder...")
            return

        AIChecked = self.AICheckBox.isChecked()

        self.progressBar.setValue(0)
        self.recordButton.setEnabled(0)
        self.abortButton.setEnabled(1)
        self.updateLog("Recording Started...")

        self.thread = QtCore.QThread()
        self.record_thread = recordThread(file_name=record_file_name, AICheckBox=AIChecked)
        self.record_thread.moveToThread(self.thread)
        self.thread.started.connect(self.record_thread.run)
        self.thread.finished.connect(self.record_thread.stop)
        self.record_thread.log_message.connect(self.updateLog)
        self.record_thread.log_values.connect(self.updateValues)
        self.thread.start()

        self.thread2 = QtCore.QThread()
        self.progress_thread = progressBarThread(recording_time_input=self.recordingTimeLineEdit.text())
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
    message = QtCore.pyqtSignal(bytearray, float)
    rx_log_message = QtCore.pyqtSignal(str)

    def __init__(self, file_name, parent=None):
        super(rxThread, self).__init__(parent)
        self.file_name = file_name.strip(".csv") + "_raw.txt"

    def run(self):
        os.system("sudo /sbin/ip link set can0 up type can bitrate 250000")
        time.sleep(0.1)
        try:
            bus = can.interface.Bus(channel='can0', bustype='socketcan_native')
        except OSError:
            self.rx_log_message.emit('Cannot find PiCAN board.')
        message = bytearray(0)
        while MainWindow.thread.isRunning():
            try:
                recv_message = bus.recv(60)
                if recv_message != None:
                    with open(self.file_name, 'a') as f:
                        data = ','.join('%02X' % byte for byte in recv_message.data)
                        central_time = datetime.datetime.fromtimestamp(float(recv_message.timestamp)).strftime(
                            '%Y-%m-%d %H:%M:%S')
                        f.write(
                            "{},{},{},{}\n".format(recv_message.timestamp, central_time, recv_message.arbitration_id,
                                                   data))
                    if recv_message.arbitration_id == 0x1CEBFF3F:
                        if recv_message.data[0] <= 0x0A:
                            message += recv_message.data[1:8]
                            
                        else:
                            message += recv_message.data[1:8]
                            
                            self.message.emit(message, float(recv_message.timestamp))
                            message = bytearray(0)
                    if recv_message.arbitration_id == 0x00FFDA3F:
                        if recv_message.data[4:8] != bytearray(b'\x8F\x06\x00\x00'):
                            self.message.emit(recv_message.data[4:8], float(recv_message.timestamp))

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

    def __init__(self, file_name, AICheckBox, parent=None):
        super(recordThread, self).__init__(parent)
        os.system("sudo /sbin/ip link set can0 down")
        self.thread = QtCore.QThread()
        self.rx_thread = rxThread(file_name=file_name)
        self.rx_thread.moveToThread(self.thread)
        self.rx_thread.message.connect(self.message_record)
        self.rx_thread.rx_log_message.connect(self.logMessage)
        self.thread.started.connect(self.rx_thread.run)
        self.file_name = file_name
        self.outfile = open(file_name, 'w')
        self.AIEnabled = AICheckBox
        with open(self.file_name, 'w') as f:
            f.write("timestamp,sweep_count,oil_RH(%),"
                    "s0_temp_post_ref(C),s0_temp_post_sample(C),s0_magnitude(Ohms),s0_phase(Deg),"
                    "s1_temp_post_ref(C),s1_temp_post_sample(C),s1_magnitude(Ohms),s1_phase(Deg),"
                    "s2_temp_post_sample(C),s2_magnitude(Ohms),s2_phase(Deg),"
                    "s3_temp_post_sample(C),s3_magnitude(Ohms),s3_phase(Deg),"
                    "s4_temp_post_sample(C),s4_magnitude(Ohms),s4_phase(Deg),"
                    "error\n")

    def run(self):
        if not self.thread.isRunning():
            self.thread.start()

    def message_record(self, message, timestamp):
        if self.thread.isRunning():
            dont_print = 0
            error = "0"
            sweep_count = 0
            oil_rh = 0
            s0_temp_post_ref = 0
            s0_temp_post_sample = 0
            s0_phase = 0
            s0_magnitude = 0
            s1_temp_post_ref = 0
            s1_temp_post_sample = 0
            s1_phase = 0
            s1_magnitude = 0
            s2_temp_post_sample = 0
            s2_phase = 0
            s2_magnitude = 0
            s3_temp_post_sample = 0
            s3_phase = 0
            s3_magnitude = 0
            s4_temp_post_sample = 0
            s4_phase = 0
            s4_magnitude = 0
            
            if len(message) == 77:
                sweep_count = up('<H', message[0:2])[0]
                oil_rh = up('<H', message[2:4])[0] / 100
                s0_temp_post_ref = (up('<f', message[4:8])[0])
                s0_temp_post_sample = (up('<f', message[8:12])[0])
                s0_magnitude = (up('<f', message[12:16])[0])
                s0_phase = (up('<f', message[16:20])[0])
                s1_temp_post_ref = (up('<f', message[20:24])[0])
                s1_temp_post_sample = (up('<f', message[24:28])[0])
                s1_magnitude = (up('<f', message[28:32])[0])
                s1_phase = (up('<f', message[32:36])[0])
                s2_temp_post_sample = (up('<f', message[36:40])[0])
                s2_magnitude = (up('<f', message[40:44])[0])
                s2_phase = (up('<f', message[44:48])[0])
                s3_temp_post_sample = (up('<f', message[48:52])[0])
                s3_magnitude = (up('<f', message[52:56])[0])
                s3_phase = (up('<f', message[56:60])[0])
                s4_temp_post_sample = (up('<f', message[60:64])[0])
                s4_magnitude = (up('<f', message[64:68])[0])
                s4_phase = (up('<f', message[68:72])[0])
                #self.log_values.emit([sweep,oil_rh,s0_temp_post_sample,s0_phase,s0_magnitude])
                self.log_message.emit("count:" + str(sweep_count) +
                      " RH:" + str(oil_rh) +
                      " temp:" + str(s0_temp_post_sample) +
                      " phase:" + str(s0_phase) +
                      " mag:" + str(s0_magnitude))
            elif len(message) == 4:
                self.log_message.emit("sensor reports error code" + str(message))
                error = str(message)
            else:
                self.log_message.emit("Canbus RX Thread Error")
                dont_print = 1

            if dont_print == 0:
                ts_formatted = datetime.datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
                with open(self.file_name, 'a') as f:
                    f.write(
                        "{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{}\n".format(
                            ts_formatted, sweep_count, oil_rh,
                            s0_temp_post_ref, s0_temp_post_sample, s0_magnitude, s0_phase,
                            s1_temp_post_ref, s1_temp_post_sample, s1_magnitude, s1_phase,
                            s2_temp_post_sample, s2_magnitude, s2_phase,
                            s3_temp_post_sample, s3_magnitude, s3_phase,
                            s4_temp_post_sample, s4_magnitude, s4_phase,
                            error))


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
                    data.append(["Time (min)"] + row[4:11] + ["Timestamp"])
                else:
                    data.append(["Time (min)"] + row[4:10] + ["Timestamp"])
            if line_count == 1:
                start_time = float(row[0])
                time = float(row[0]) - start_time
                time_data.append(time)
                if (self.AIEnabled == 1):
                    RH_data = list(map(float, row[10:11]))
                sensor_data = list(map(float, row[4:10]))
                formatted_data = sensor_data

            if line_count > 1:
                time = float(row[0]) - start_time
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
                        data.append(
                            [time_data[line_count - 2] / 60] + formatted_data[0:6] + [RH_data[0]] + [central_time])
                    else:
                        data.append([time_data[line_count - 2] / 60] + formatted_data[0:6] + [central_time])

                    formatted_data = sensor_data
            line_count += 1

        if (self.AIEnabled == 1):
            data.append([time / 60] + formatted_data[0:6] + [RH_data[0]] + [central_time])
        else:
            data.append([time / 60] + formatted_data + [central_time])

        print("creating " + self.file_name.strip(".txt") + ".csv")
        with open(self.file_name.strip(".txt") + ".csv", 'w', newline='') as csvfile:
            csv_writer = csv.writer(csvfile, delimiter=',')
            csv_writer.writerows(data)

    def stop(self):
        self.thread.quit()
        self.thread.wait()
        self.outfile.close()
        #self.format_file()
        os.system("sudo /sbin/ip link set can0 down")


class progressBarThread(QtCore.QObject):
    timeout = QtCore.pyqtSignal()
    updateProgressBar = QtCore.pyqtSignal(float)

    def __init__(self, recording_time_input, parent=None):
        super(progressBarThread, self).__init__(parent)
        self.recording_time_input = recording_time_input

    def run(self):
        progress = 0
        try:
            recording_time = 60 * (int(self.recording_time_input))
        except ValueError:
            print("not a valid recording time")
            return
        while progress < 100 and MainWindow.thread.isRunning():
            QtCore.QThread.sleep(1)
            if not MainWindow.thread.isRunning():
                return
            progress += 100.0 / recording_time
            self.updateProgressBar.emit(progress)
        self.timeout.emit()

    def quit(self):
        print("stop")


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    MainWindow = MainUiClass()
    MainWindow.show()
    sys.exit(app.exec())