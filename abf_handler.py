"""
ABF File Handler
Handles loading, parsing, and managing ABF files using pyABF
"""
import pyabf
import numpy as np
from typing import Optional, List, Dict, Tuple
from dataclasses import dataclass


@dataclass
class SweepData:
    """Container for sweep data"""
    sweep_number: int
    channel: int
    time: np.ndarray
    data: np.ndarray
    command: np.ndarray
    sample_rate: float


@dataclass
class ProtocolInfo:
    """Container for protocol information"""
    name: str
    adc_units: List[str]
    dac_units: List[str]
    sample_rate: float
    sweep_count: int
    sweep_length_sec: float


class ABFHandler:
    """Handles ABF file operations"""
    
    def __init__(self, file_path: Optional[str] = None):
        self.file_path = file_path
        self.abf: Optional[pyabf.ABF] = None
        self._current_sweep = 0
        self._current_channel = 0
        
        if file_path:
            self.load_file(file_path)
    
    def load_file(self, file_path: str) -> bool:
        """Load an ABF file"""
        try:
            self.abf = pyabf.ABF(file_path)
            self.file_path = file_path
            self._current_sweep = 0
            self._current_channel = 0
            return True
        except Exception as e:
            print(f"Error loading ABF file: {e}")
            return False
    
    @property
    def is_loaded(self) -> bool:
        """Check if a file is loaded"""
        return self.abf is not None
    
    @property
    def channel_count(self) -> int:
        """Get number of channels"""
        if not self.is_loaded:
            return 0
        return self.abf.channelCount
    
    @property
    def sweep_count(self) -> int:
        """Get number of sweeps"""
        if not self.is_loaded:
            return 0
        return self.abf.sweepCount
    
    @property
    def sample_rate(self) -> float:
        """Get sample rate in Hz"""
        if not self.is_loaded:
            return 0
        return self.abf.dataRate
    
    @property
    def sweep_length_sec(self) -> float:
        """Get sweep length in seconds"""
        if not self.is_loaded:
            return 0
        return self.abf.sweepLengthSec
    
    @property
    def protocol_name(self) -> str:
        """Get protocol name"""
        if not self.is_loaded:
            return ""
        return getattr(self.abf, 'protocol', 'Unknown')
    
    def get_protocol_info(self) -> ProtocolInfo:
        """Get protocol information"""
        if not self.is_loaded:
            return ProtocolInfo("", [], [], 0, 0, 0)
        
        adc_units = []
        dac_units = []
        for i in range(self.channel_count):
            try:
                adc_units.append(self.abf.adcUnits[i])
            except:
                adc_units.append("")
            try:
                dac_units.append(self.abf.dacUnits[i] if i < len(self.abf.dacUnits) else "")
            except:
                dac_units.append("")
        
        return ProtocolInfo(
            name=self.protocol_name,
            adc_units=adc_units,
            dac_units=dac_units,
            sample_rate=self.sample_rate,
            sweep_count=self.sweep_count,
            sweep_length_sec=self.sweep_length_sec
        )
    
    def get_sweep(self, sweep_number: int, channel: int = 0) -> Optional[SweepData]:
        """Get sweep data for specified sweep and channel"""
        if not self.is_loaded:
            return None
        
        if sweep_number < 0 or sweep_number >= self.sweep_count:
            return None
        
        if channel < 0 or channel >= self.channel_count:
            return None
        
        try:
            self.abf.setSweep(sweepNumber=sweep_number, channel=channel)
            
            return SweepData(
                sweep_number=sweep_number,
                channel=channel,
                time=self.abf.sweepX,
                data=self.abf.sweepY,
                command=self.abf.sweepC if hasattr(self.abf, 'sweepC') else np.zeros_like(self.abf.sweepX),
                sample_rate=self.sample_rate
            )
        except Exception as e:
            print(f"Error getting sweep: {e}")
            return None
    
    def get_all_sweeps(self, channel: int = 0) -> List[SweepData]:
        """Get all sweeps for a channel"""
        if not self.is_loaded:
            return []
        
        sweeps = []
        for i in range(self.sweep_count):
            sweep = self.get_sweep(i, channel)
            if sweep:
                sweeps.append(sweep)
        return sweeps
    
    def set_current_sweep(self, sweep_number: int):
        """Set current sweep"""
        if 0 <= sweep_number < self.sweep_count:
            self._current_sweep = sweep_number
    
    def set_current_channel(self, channel: int):
        """Set current channel"""
        if 0 <= channel < self.channel_count:
            self._current_channel = channel
    
    @property
    def current_sweep(self) -> int:
        return self._current_sweep
    
    @property
    def current_channel(self) -> int:
        return self._current_channel
    
    def get_file_info(self) -> Dict:
        """Get file metadata"""
        if not self.is_loaded:
            return {}
        
        info = {
            'filename': self.abf.abfFilePath,
            'protocol': getattr(self.abf, 'protocol', 'Unknown'),
            'channels': self.channel_count,
            'sweeps': self.sweep_count,
            'sample_rate': self.sample_rate,
            'sweep_length': self.sweep_length_sec,
            'date': getattr(self.abf, 'abfDateTime', 'Unknown'),
        }
        
        # Add channel-specific info
        info['channel_info'] = []
        for i in range(self.channel_count):
            channel_info = {
                'index': i,
                'adc_units': self.abf.adcUnits[i] if i < len(self.abf.adcUnits) else "",
                'dac_units': self.abf.dacUnits[i] if i < len(self.abf.dacUnits) else "",
            }
            info['channel_info'].append(channel_info)
        
        return info

