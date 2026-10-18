#  -------------------------------------------------------------------------------------------------
#  Copyright (C) 2025 Matías Rubén Bolaños Wagner
#  SPDX-License-Identifier: GPL-3.0-or-later
#  ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- --
from pynq import Overlay, MMIO, GPIO
import os

PHASE_REF_CHANNEL = 0  #: Channel 0 is the phase reference (no fine phase control)
PHASE_MAX_CODES = 63  #: Fine phase range in TX PI codes (1 UI = 64 codes, coarser shifts use the delay)
PHASE_APPLY = 1 << 16
PHASE_REALIGN = 1 << 17
PHASE_RESET = 1 << 31

class zPulseOverlay(Overlay):
    def __init__(self, bitfile_name=None, **kwargs):
        """Construct a new zPulseOverlay

        bitfile_name: path to the bitstream file. Should have the .hwh file in the same directory as the .bit file with the same name.

        """
        super().__init__(bitfile_name, **kwargs)
        
        board = os.environ['BOARD']
        
        self.ch_player = {}
        self.ch_enable = {}
        self.addr_limit = {}
        # Check which DAC channels are enabled (from 0 to 7 based on DAC_ENABLED)
        for i in range(8):
            self.ch_player[i] = self.memdict_to_view(f"tx_channels/tx_channel_{i}/axi_bram_ctrl_0")
        self.ch_enable[0] = self.tx_channels.tx_channel_0.channel_ctrl_0.channel2[0]
        self.ch_enable[1] = self.tx_channels.tx_channel_1.channel_ctrl_0.channel2[0]
        self.ch_enable[2] = self.tx_channels.tx_channel_2.channel_ctrl_0.channel2[0]
        self.ch_enable[3] = self.tx_channels.tx_channel_3.channel_ctrl_0.channel2[0]
        self.ch_enable[4] = self.tx_channels.tx_channel_4.channel_ctrl_0.channel2[0]
        self.ch_enable[5] = self.tx_channels.tx_channel_5.channel_ctrl_0.channel2[0]
        self.ch_enable[6] = self.tx_channels.tx_channel_6.channel_ctrl_0.channel2[0]
        self.ch_enable[7] = self.tx_channels.tx_channel_7.channel_ctrl_0.channel2[0]
        
        self.addr_limit[0] = self.tx_channels.tx_channel_0.channel_ctrl_0.channel1
        self.addr_limit[1] = self.tx_channels.tx_channel_1.channel_ctrl_0.channel1
        self.addr_limit[2] = self.tx_channels.tx_channel_2.channel_ctrl_0.channel1
        self.addr_limit[3] = self.tx_channels.tx_channel_3.channel_ctrl_0.channel1
        self.addr_limit[4] = self.tx_channels.tx_channel_4.channel_ctrl_0.channel1
        self.addr_limit[5] = self.tx_channels.tx_channel_5.channel_ctrl_0.channel1
        self.addr_limit[6] = self.tx_channels.tx_channel_6.channel_ctrl_0.channel1
        self.addr_limit[7] = self.tx_channels.tx_channel_7.channel_ctrl_0.channel1

        # Fine phase control (TX phase interpolator), channels 1 to 7
        self.phase_ctrl = {}
        self.phase_status = {}
        self._phase_target = {}
        for i in range(8):
            if i == PHASE_REF_CHANNEL:
                continue
            phase_gpio = getattr(self.tx_channels, f"tx_channel_{i}").phase_ctrl_0
            self.phase_ctrl[i] = phase_gpio.channel1
            self.phase_status[i] = phase_gpio.channel2
            self._phase_target[i] = 0

    def reset(self):
        self.reset_gpio.channel1[0].on()
        self.reset_gpio.channel1[0].off()
        
    def enable_channel(self, ch_index=None):
        if (isinstance(ch_index, int) and 0 <= ch_index <= 7):
            self.ch_enable[ch_index].on()
        
    def disable_channel(self, ch_index=None):
        if (isinstance(ch_index, int) and 0 <= ch_index <= 7):
            zero_waveform = [0] * self.ch_player[ch_index].shape[0]
            self.ch_player[ch_index][:] = zero_waveform
            self.ch_enable[ch_index].off()
                    
    def has_phase_control(self, ch_index=None):
        return ch_index in self.phase_ctrl

    def set_phase(self, ch_index, codes):
        """Set the fine phase offset of a channel in TX PI codes (relative to the aligned phase).

        The setpoint is held in the PL, so it survives reset() (which clears the AXI GPIOs).
        """
        if not self.has_phase_control(ch_index):
            raise ValueError(f"Channel {ch_index} has no phase control (channel {PHASE_REF_CHANNEL} is the reference)")
        codes = int(codes)
        if not 0 <= codes <= PHASE_MAX_CODES:
            raise ValueError(f"Phase must be between 0 and {PHASE_MAX_CODES} codes")
        self._phase_target[ch_index] = codes
        self.phase_ctrl[ch_index].write(codes | PHASE_APPLY, 0xFFFFFFFF)

    def get_phase_status(self, ch_index):
        status = self.phase_status[ch_index].read()
        return {
            "offset": status & 0x7F,
            "raw": (status >> 8) & 0x7F,
            "aligned": bool(status >> 16 & 1),
            "busy": bool(status >> 17 & 1),
            "tx_reset_done": bool(status >> 18 & 1),
        }

    def _phase_pulse(self, ch_index, flag):
        target = self._phase_target[ch_index]
        self.phase_ctrl[ch_index].write(target | flag, 0xFFFFFFFF)
        self.phase_ctrl[ch_index].write(target | PHASE_APPLY, 0xFFFFFFFF)

    def fine_realign_phase(self, ch_index):
        """Redo only the fine alignment of a channel to the half-response of its phase detector."""
        self._phase_pulse(ch_index, PHASE_REALIGN)

    def realign_phase(self, ch_index):
        """Restart the automatic alignment of a channel (the phase offset is re-applied afterwards)."""
        self._phase_pulse(ch_index, PHASE_RESET)

    def memdict_to_view(self, ip, dtype='int32'):
        """ Configures access to internal memory via MMIO"""
        baseAddress = self.mem_dict[ip]["phys_addr"]
        mem_range = self.mem_dict[ip]["addr_range"]
        ipmmio = MMIO(baseAddress, mem_range)
        return ipmmio.array[0:ipmmio.length].view(dtype)
    
        
        
    