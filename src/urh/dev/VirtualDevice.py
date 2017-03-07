import time
from enum import Enum

import numpy as np
from PyQt5.QtCore import pyqtSignal, QObject

from urh.dev.BackendHandler import Backends, BackendHandler
from urh.dev.gr.ReceiverThread import ReceiverThread
from urh.dev.gr.SenderThread import SenderThread
from urh.dev.gr.SpectrumThread import SpectrumThread
from urh.plugins.NetworkSDRInterface.NetworkSDRInterfacePlugin import NetworkSDRInterfacePlugin
from urh.util.Logger import logger


class Mode(Enum):
    receive = 1
    send = 2
    spectrum = 3


class VirtualDevice(QObject):
    """
    Wrapper class for providing sending methods for grc and native devices

    """
    started = pyqtSignal()
    stopped = pyqtSignal()
    index_changed = pyqtSignal(int, int)
    sender_needs_restart = pyqtSignal()

    def __init__(self, backend_handler, name: str, mode: Mode, bw, freq, gain, samp_rate, samples_to_send=None,
                 device_ip=None, sending_repeats=1, parent=None, is_ringbuffer=False, raw_mode=True, portnumber=1234):
        super().__init__(parent)
        self.name = name
        self.mode = mode
        self.backend_handler = backend_handler

        if self.name == NetworkSDRInterfacePlugin.NETWORK_SDR_NAME:
            self.backend = Backends.network
        else:
            try:
                self.backend = self.backend_handler.device_backends[name.lower()].selected_backend
            except KeyError:
                logger.warning("Invalid device name: {0}".format(name))
                self.backend = Backends.none
                self.__dev = None
                return

        if self.backend == Backends.grc:
            if mode == Mode.receive:
                self.__dev = ReceiverThread(samp_rate, freq, gain, bw, parent=parent, is_ringbuffer=is_ringbuffer)
                self.__dev.index_changed.connect(self.emit_index_changed)
            elif mode == Mode.send:
                self.__dev = SenderThread(samp_rate, freq, gain, bw, parent=parent)
                self.__dev.data = samples_to_send
                self.__dev.samples_per_transmission = len(samples_to_send)
            elif mode == Mode.spectrum:
                self.__dev = SpectrumThread(samp_rate, freq, gain, bw, parent=parent)
            else:
                raise ValueError("Unknown mode")
            self.__dev.usrp_ip = device_ip
            self.__dev.device = name
            self.__dev.started.connect(self.emit_started_signal)
            self.__dev.stopped.connect(self.emit_stopped_signal)
            self.__dev.sender_needs_restart.connect(self.emit_sender_needs_restart)
        elif self.backend == Backends.native:
            name = self.name.lower()
            if name in map(str.lower, BackendHandler.DEVICE_NAMES):
                is_ringbuffer = self.mode == Mode.spectrum or is_ringbuffer

                if name == "hackrf":
                    from urh.dev.native.HackRF import HackRF
                    self.__dev = HackRF(bw, freq, gain, samp_rate, is_ringbuffer=is_ringbuffer)
                elif name.replace("-", "") == "rtlsdr":
                    from urh.dev.native.RTLSDR import RTLSDR
                    self.__dev = RTLSDR(freq, gain, samp_rate, device_number=0, is_ringbuffer=is_ringbuffer)
                elif name.replace("-", "") == "rtltcp":
                    from urh.dev.native.RTLSDRTCP import RTLSDRTCP
                    self.__dev = RTLSDRTCP(freq, gain, samp_rate, device_number=0, is_ringbuffer=is_ringbuffer)
                else:
                    raise NotImplementedError("Native Backend for {0} not yet implemented".format(name))
            else:
                raise ValueError("Unknown device name {0}".format(name))
            self.__dev.portnumber = portnumber
            self.__dev.device_ip = device_ip
            self.__dev.rcv_index_changed.connect(self.emit_index_changed)
            if mode == Mode.send:
                self.__dev.init_send_parameters(samples_to_send, sending_repeats, skip_device_parameters=True)
        elif self.backend == Backends.network:
            self.__dev = NetworkSDRInterfacePlugin(raw_mode=raw_mode)
            self.__dev.rcv_index_changed.connect(self.emit_index_changed)
            self.__dev.samples_to_send = samples_to_send
        elif self.backend == Backends.none:
            self.__dev = None
        else:
            raise ValueError("Unsupported Backend")

    @property
    def bandwidth(self):
        return self.__dev.bandwidth

    @bandwidth.setter
    def bandwidth(self, value):
        self.__dev.bandwidth = value

    @property
    def bandwidth_is_adjustable(self):
        if self.backend == Backends.grc:
            return True
        elif self.backend == Backends.native:
            return self.__dev.bandwidth_is_adjustable
        elif self.backend == Backends.network:
            return True
        else:
            raise ValueError("Unsupported Backend")

    @property
    def frequency(self):
        if self.backend == Backends.grc:
            return self.__dev.freq
        elif self.backend == Backends.native:
            return self.__dev.frequency
        else:
            raise ValueError("Unsupported Backend")

    @frequency.setter
    def frequency(self, value):
        if self.backend == Backends.grc:
            self.__dev.freq = value
        elif self.backend == Backends.native:
            self.__dev.frequency = value
        elif self.backend == Backends.network:
            pass
        else:
            raise ValueError("Unsupported Backend")

    @property
    def gain(self):
        return self.__dev.gain

    @gain.setter
    def gain(self, value):
        self.__dev.gain = value

    @property
    def sample_rate(self):
        return self.__dev.sample_rate

    @sample_rate.setter
    def sample_rate(self, value):
        self.__dev.sample_rate = value

    @property
    def samples_to_send(self):
        if self.backend == Backends.grc:
            return self.__dev.data
        elif self.backend in (Backends.native, Backends.network):
            return self.__dev.samples_to_send
        else:
            raise ValueError("Unsupported Backend")

    @samples_to_send.setter
    def samples_to_send(self, value):
        if self.backend == Backends.grc:
            self.__dev.data = value
        elif self.backend == Backends.native:
            self.__dev.init_send_parameters(value, self.num_sending_repeats, skip_device_parameters=True)
        elif self.backend == Backends.network:
            self.__dev.samples_to_send = value
        else:
            raise ValueError("Unsupported Backend")

    @property
    def ip(self):
        if self.backend == Backends.grc:
            return self.__dev.usrp_ip
        elif self.backend == Backends.native:
            return self.__dev.device_ip
        else:
            raise ValueError("Unsupported Backend")

    @ip.setter
    def ip(self, value):
        if self.backend == Backends.grc:
            self.__dev.usrp_ip = value
        elif self.backend == Backends.native:
            self.__dev.device_ip = value
        elif self.backend in (Backends.none, Backends.network):
            pass
        else:
            raise ValueError("Unsupported Backend")

    @property
    def port(self):
        if self.backend == Backends.grc:
            return self.__dev.port
        else:
            raise ValueError("Port only for gnuradio socket (grc backend)")

    @port.setter
    def port(self, value):
        if self.backend == Backends.grc:
            self.__dev.port = value
        else:
            raise ValueError("Port only for gnuradio socket (grc backend)")

    @property
    def data(self):
        if self.backend == Backends.grc:
            return self.__dev.data
        elif self.backend == Backends.native:
            if self.mode == Mode.send:
                return self.__dev.samples_to_send
            else:
                return self.__dev.receive_buffer
        elif self.backend == Backends.network:
            if self.mode == Mode.send:
                raise NotImplementedError("Todo")
            else:
                if self.__dev.raw_mode:
                    return self.__dev.receive_buffer
                else:
                    return self.__dev.received_bits
        else:
            raise ValueError("Unsupported Backend")

    @data.setter
    def data(self, value):
        if self.backend == Backends.grc:
            self.__dev.data = value
        elif self.backend == Backends.native:
            if self.mode == Mode.send:
                self.__dev.samples_to_send = value
            else:
                self.__dev.receive_buffer = value
        else:
            raise ValueError("Unsupported Backend")

    def free_data(self):
        if self.backend == Backends.grc:
            del self.__dev.data
        elif self.backend == Backends.native:
            del self.__dev.samples_to_send
            del self.__dev.receive_buffer
        elif self.backend == Backends.network:
            self.__dev.free_data()
        elif self.backend == Backends.none:
            pass
        else:
            raise ValueError("Unsupported Backend")

    @property
    def num_sending_repeats(self):
        if self.mode == Mode.send:
            if self.backend == Backends.grc:
                return self.__dev.max_repeats
            elif self.backend == Backends.native:
                return self.__dev.sending_repeats
            else:
                raise ValueError("Unsupported Backend")

    @num_sending_repeats.setter
    def num_sending_repeats(self, value):
        if self.mode == Mode.send:
            if self.backend == Backends.grc:
                if value != self.__dev.max_repeats:
                    self.__dev.max_repeats = value
                    self.__dev.current_iteration = 0
            elif self.backend in (Backends.native, Backends.network):
                self.__dev.sending_repeats = value
            else:
                raise ValueError("Unsupported Backend")

    @property
    def current_index(self):
        if self.backend == Backends.grc:
            return self.__dev.current_index
        elif self.backend == Backends.native:
            if self.mode == Mode.send:
                return self.__dev.current_sent_sample
            else:
                return self.__dev.current_recv_index
        elif self.backend == Backends.network:
            if self.mode == Mode.send:
                return self.__dev.current_sent_sample
            else:
                return self.__dev.current_receive_index
        else:
            raise ValueError("Unsupported Backend")

    @current_index.setter
    def current_index(self, value):
        if self.backend == Backends.grc:
            self.__dev.current_index = value
        elif self.backend == Backends.native:
            if self.mode == Mode.send:
                self.__dev.current_sent_sample = value
            else:
                self.__dev.current_recv_index = value
        elif self.backend == Backends.network:
            if self.mode == Mode.send:
                self.__dev.current_sent_sample = value
            else:
                self.__dev.current_receive_index = value
        else:
            raise ValueError("Unsupported Backend")

    @property
    def current_iteration(self):
        if self.backend == Backends.grc:
            return self.__dev.current_iteration
        elif self.backend in (Backends.native, Backends.network):
            return self.__dev.current_sending_repeat
        else:
            raise ValueError("Unsupported Backend")

    @current_iteration.setter
    def current_iteration(self, value):
        if self.backend == Backends.grc:
            self.__dev.current_iteration = value
        elif self.backend in (Backends.native, Backends.network):
            self.__dev.current_sending_repeat = value
        else:
            raise ValueError("Unsupported Backend")

    @property
    def sending_finished(self):
        if self.backend == Backends.grc:
            return self.__dev.current_iteration is None
        elif self.backend == Backends.native:
            return self.__dev.sending_finished
        elif self.backend == Backends.network:
            return self.__dev.current_sent_sample == len(self.samples_to_send)
        else:
            raise ValueError("Unsupported Backend")

    @property
    def spectrum(self):
        if self.mode == Mode.spectrum:
            if self.backend == Backends.grc:
                return self.__dev.x, self.__dev.y
            elif self.backend == Backends.native:
                w = np.abs(np.fft.fft(self.__dev.receive_buffer))
                freqs = np.fft.fftfreq(len(w), 1 / self.sample_rate)
                idx = np.argsort(freqs)
                return freqs[idx].astype(np.float32), w[idx].astype(np.float32)
        else:
            raise ValueError("Spectrum x only available in spectrum mode")

    def start(self):
        if self.backend == Backends.grc:
            self.__dev.setTerminationEnabled(True)
            self.__dev.terminate()
            time.sleep(0.1)
            self.__dev.start()  # Already connected to started signal in constructor
        elif self.backend == Backends.native:
            if self.mode == Mode.send:
                self.__dev.start_tx_mode(resume=True)
            else:
                self.__dev.start_rx_mode()

            self.emit_started_signal()
        elif self.backend == Backends.network:
            if self.mode == Mode.receive:
                self.__dev.start_tcp_server_for_receiving()
            else:
                self.__dev.start_raw_sending_thread()

            self.emit_started_signal()
        else:
            raise ValueError("Unsupported Backend")

    def stop(self, msg: str):
        if self.backend == Backends.grc:
            self.__dev.stop(msg)  # Already connected to stopped in constructor
        elif self.backend == Backends.native:
            if self.mode == Mode.send:
                self.__dev.stop_tx_mode(msg)
            else:
                self.__dev.stop_rx_mode(msg)
            self.emit_stopped_signal()
        elif self.backend == Backends.network:
            self.__dev.stop_tcp_server()
            self.emit_stopped_signal()
        elif self.backend == Backends.none:
            pass
        else:
            logger.error("Stop device: Unsupported backend " + str(self.backend))

    def stop_on_error(self, msg: str):
        if self.backend == Backends.grc:
            self.__dev.stop(msg)  # Already connected to stopped in constructor
        elif self.backend == Backends.native:
            self.read_errors()  # Clear errors
            self.__dev.stop_rx_mode("Stop on error")
            self.__dev.stop_tx_mode("Stop on error")
            self.emit_stopped_signal()
        else:
            raise ValueError("Unsupported Backend")

    def cleanup(self):
        if self.backend == Backends.grc:
            if self.mode == Mode.send:
                self.__dev.socket.close()
                time.sleep(0.1)
            self.__dev.quit()
            self.data = None

        elif self.backend == Backends.native:
            self.data = None

        elif self.backend == Backends.none:
            pass

        else:
            raise ValueError("Unsupported Backend")

    def emit_stopped_signal(self):
        self.stopped.emit()

    def emit_started_signal(self):
        self.started.emit()

    def emit_sender_needs_restart(self):
        self.sender_needs_restart.emit()

    def emit_index_changed(self, old, new):
        self.index_changed.emit(old, new)

    def read_errors(self):
        if self.backend == Backends.grc:
            return self.__dev.read_errors()
        elif self.backend == Backends.native:
            errors = "\n\n".join(self.__dev.errors)
            self.__dev.errors.clear()
            return errors
        elif self.backend == Backends.network:
            return ""
        else:
            raise ValueError("Unsupported Backend")

    def set_server_port(self, port: int):
        if self.backend == Backends.network:
            self.__dev.server_port = port
        else:
            raise ValueError("Setting port only supported for NetworkSDR Plugin")

    def set_client_port(self, port: int):
        if self.backend == Backends.network:
            self.__dev.client_port = port
        else:
            raise ValueError("Setting port only supported for NetworkSDR Plugin")
