"""
Analysis Tools
Provides various analysis functions for electrophysiology data
"""
import numpy as np
from typing import List, Tuple, Optional, Dict
from dataclasses import dataclass
from scipy import signal
from scipy.optimize import curve_fit
from scipy.ndimage import gaussian_filter1d


@dataclass
class Peak:
    """Container for peak information"""
    index: int
    time: float
    value: float
    is_max: bool  # True for peak, False for trough


@dataclass
class Measurement:
    """Container for cursor measurements"""
    x1: float
    y1: float
    x2: float
    y2: float
    delta_x: float
    delta_y: float
    slope: float


class AnalysisTools:
    """Collection of analysis tools for electrophysiology data"""
    
    @staticmethod
    def find_peaks(data: np.ndarray, time: np.ndarray, 
                   height: Optional[float] = None,
                   distance: Optional[int] = None,
                   prominence: Optional[float] = None,
                   find_max: bool = True) -> List[Peak]:
        """
        Find peaks or troughs in data
        
        Args:
            data: Data array
            time: Time array
            height: Minimum peak height
            distance: Minimum distance between peaks (in samples)
            prominence: Minimum peak prominence
            find_max: If True, find peaks; if False, find troughs
        
        Returns:
            List of Peak objects
        """
        if find_max:
            peaks, properties = signal.find_peaks(data, height=height, 
                                                  distance=distance, 
                                                  prominence=prominence)
        else:
            peaks, properties = signal.find_peaks(-data, height=-height if height else None,
                                                  distance=distance,
                                                  prominence=prominence)
            # Convert back to actual values
            if len(peaks) > 0:
                properties['peak_heights'] = data[peaks]
        
        result = []
        for i, peak_idx in enumerate(peaks):
            result.append(Peak(
                index=int(peak_idx),
                time=time[peak_idx],
                value=data[peak_idx],
                is_max=find_max
            ))
        
        return result
    
    @staticmethod
    def calculate_measurement(x1: float, y1: float, 
                             x2: float, y2: float) -> Measurement:
        """Calculate measurement between two cursor points"""
        delta_x = x2 - x1
        delta_y = y2 - y1
        slope = delta_y / delta_x if delta_x != 0 else 0.0
        
        return Measurement(
            x1=x1, y1=y1,
            x2=x2, y2=y2,
            delta_x=delta_x,
            delta_y=delta_y,
            slope=slope
        )
    
    @staticmethod
    def calculate_statistics(data: np.ndarray) -> Dict:
        """Calculate basic statistics for data"""
        return {
            'mean': np.mean(data),
            'std': np.std(data),
            'min': np.min(data),
            'max': np.max(data),
            'median': np.median(data),
            'q25': np.percentile(data, 25),
            'q75': np.percentile(data, 75),
            'range': np.max(data) - np.min(data),
            'variance': np.var(data)
        }
    
    @staticmethod
    def calculate_area_under_curve(data: np.ndarray, time: np.ndarray,
                                   start_idx: Optional[int] = None,
                                   end_idx: Optional[int] = None) -> float:
        """Calculate area under curve (integral)"""
        if start_idx is None:
            start_idx = 0
        if end_idx is None:
            end_idx = len(data)
        
        # Use trapezoidal rule
        area = np.trapz(data[start_idx:end_idx], time[start_idx:end_idx])
        return area
    
    @staticmethod
    def detect_events(data: np.ndarray, time: np.ndarray,
                     threshold: float, 
                     direction: str = 'above',
                     min_duration: float = 0.0) -> List[Tuple[int, int]]:
        """
        Detect events crossing a threshold
        
        Args:
            data: Data array
            time: Time array
            threshold: Threshold value
            direction: 'above' or 'below'
            min_duration: Minimum event duration in seconds
        
        Returns:
            List of (start_idx, end_idx) tuples for each event
        """
        if direction == 'above':
            mask = data > threshold
        else:
            mask = data < threshold
        
        # Find transitions
        diff = np.diff(mask.astype(int))
        starts = np.where(diff == 1)[0]
        ends = np.where(diff == -1)[0]
        
        # Handle edge cases
        if mask[0]:
            starts = np.concatenate([[0], starts])
        if mask[-1]:
            ends = np.concatenate([ends, [len(mask) - 1]])
        
        # Filter by minimum duration
        events = []
        min_samples = int(min_duration * (len(time) / (time[-1] - time[0])))
        
        for start, end in zip(starts, ends):
            if end - start >= min_samples:
                events.append((int(start), int(end)))
        
        return events
    
    @staticmethod
    def calculate_rise_time(data: np.ndarray, time: np.ndarray,
                           peak_idx: int,
                           baseline_percent: float = 10,
                           peak_percent: float = 90) -> Optional[float]:
        """
        Calculate rise time from baseline to peak
        
        Args:
            data: Data array
            time: Time array
            peak_idx: Index of the peak
            baseline_percent: Percentile to use as baseline (e.g., 10 = 10%)
            peak_percent: Percentile to use as peak (e.g., 90 = 90%)
        
        Returns:
            Rise time in seconds, or None if calculation fails
        """
        if peak_idx <= 0 or peak_idx >= len(data):
            return None
        
        # Find baseline value (before peak)
        baseline_data = data[:peak_idx]
        baseline_value = np.percentile(baseline_data, baseline_percent)
        peak_value = data[peak_idx]
        
        # Calculate target values
        target_low = baseline_value + (peak_value - baseline_value) * (baseline_percent / 100)
        target_high = baseline_value + (peak_value - baseline_value) * (peak_percent / 100)
        
        # Find indices where data crosses these targets
        rising_portion = data[:peak_idx + 1]
        
        # Find 10% crossing
        low_crossings = np.where(np.diff((rising_portion >= target_low).astype(int)) == 1)[0]
        # Find 90% crossing
        high_crossings = np.where(np.diff((rising_portion >= target_high).astype(int)) == 1)[0]
        
        if len(low_crossings) > 0 and len(high_crossings) > 0:
            low_idx = low_crossings[-1]
            high_idx = high_crossings[-1]
            if high_idx > low_idx:
                return time[high_idx] - time[low_idx]
        
        return None
    
    @staticmethod
    def calculate_decay_time(data: np.ndarray, time: np.ndarray,
                            peak_idx: int,
                            decay_percent: float = 63.2) -> Optional[float]:
        """
        Calculate decay time constant (tau)
        
        Args:
            data: Data array
            time: Time array
            peak_idx: Index of the peak
            decay_percent: Percent decay (63.2 for tau, 50 for half-life)
        
        Returns:
            Decay time in seconds, or None if calculation fails
        """
        if peak_idx < 0 or peak_idx >= len(data) - 1:
            return None
        
        peak_value = data[peak_idx]
        target_value = peak_value * (1 - decay_percent / 100)
        
        # Look for crossing point after peak
        decay_portion = data[peak_idx:]
        decay_time = time[peak_idx:]
        
        # Find where data crosses target
        below_target = decay_portion < target_value
        if np.any(below_target):
            decay_idx = np.where(below_target)[0][0]
            return decay_time[decay_idx] - decay_time[0]
        
        return None
    
    @staticmethod
    def baseline_subtract(data: np.ndarray, 
                         start_idx: int = 0,
                         end_idx: Optional[int] = None) -> np.ndarray:
        """Subtract baseline from data"""
        if end_idx is None:
            end_idx = len(data)
        
        baseline = np.mean(data[start_idx:end_idx])
        return data - baseline
    
    @staticmethod
    def filter_data(data: np.ndarray, 
                   filter_type: str = 'lowpass',
                   cutoff: float = 1000.0,
                   sample_rate: float = 10000.0,
                   order: int = 4) -> np.ndarray:
        """
        Filter data using Butterworth filter
        
        Args:
            data: Data array
            filter_type: 'lowpass', 'highpass', or 'bandpass'
            cutoff: Cutoff frequency (Hz) or (low, high) tuple for bandpass
            sample_rate: Sample rate in Hz
            order: Filter order
        
        Returns:
            Filtered data
        """
        nyquist = sample_rate / 2
        
        if filter_type == 'lowpass':
            b, a = signal.butter(order, cutoff / nyquist, 'low')
        elif filter_type == 'highpass':
            b, a = signal.butter(order, cutoff / nyquist, 'high')
        elif filter_type == 'bandpass':
            low, high = cutoff
            b, a = signal.butter(order, [low / nyquist, high / nyquist], 'band')
        else:
            return data
        
        return signal.filtfilt(b, a, data)
    
    @staticmethod
    def gaussian_lowpass_filter(data: np.ndarray,
                                cutoff_freq: float = 1000.0,
                                sample_rate: float = 10000.0) -> np.ndarray:
        """
        Apply Gaussian lowpass filter to data
        
        The Gaussian filter is implemented using convolution with a Gaussian kernel.
        The cutoff frequency is defined as the -3dB point. For a Gaussian filter,
        the sigma parameter is related to the cutoff frequency by:
        sigma = sample_rate / (2 * pi * cutoff_freq) for the -3dB point
        
        Args:
            data: Data array
            cutoff_freq: Cutoff frequency in Hz (where response is -3dB)
            sample_rate: Sample rate in Hz
        
        Returns:
            Filtered data
        """
        if cutoff_freq <= 0 or sample_rate <= 0:
            return data
        
        # Calculate sigma for Gaussian filter
        # For a Gaussian lowpass filter, the -3dB point is at the cutoff frequency.
        # The relationship between cutoff frequency and sigma (in time) is:
        # sigma_time = √ln(2) / (2π * fc) ≈ 0.1325 / fc
        # where fc is the cutoff frequency in Hz.
        #
        # Since gaussian_filter1d uses sigma in units of samples (not time),
        # we need to convert: sigma_samples = sigma_time * sample_rate
        #
        # Therefore: sigma_samples = 0.1325 * sample_rate / cutoff_freq
        
        if cutoff_freq >= sample_rate / 2:
            # Can't filter above Nyquist
            return data
        
        # Calculate sigma in samples
        # sigma_samples = 0.1325 * sample_rate / cutoff_freq
        # This gives us the -3dB point at cutoff_freq
        sigma_samples = 0.1325 * sample_rate / cutoff_freq
        
        # Apply Gaussian filter using scipy's gaussian_filter1d
        # This uses convolution with a Gaussian kernel
        filtered_data = gaussian_filter1d(data, sigma=sigma_samples, mode='reflect')
        
        return filtered_data


class BlockDetector:
    """Detects blocking events in single-channel recordings"""
    
    @staticmethod
    def detect_blocks(data: np.ndarray,
                     time: np.ndarray,
                     baseline_threshold: float = None,
                     block_threshold_factor: float = 2.0,
                     min_block_duration: float = 0.001) -> List[Dict]:
        """
        Detect block events in a single trace
        
        Block events are periods where the current moves toward 0 pA from the baseline.
        - If baseline is negative (e.g., -0.25 pA), blocks are values closer to 0 (less negative, e.g., -0.1 pA)
        - If baseline is positive (e.g., 0.25 pA), blocks are values closer to 0 (less positive, e.g., 0.1 pA)
        - Blocks are always between baseline and 0, moving toward 0
        
        Args:
            data: Current data array
            time: Time array
            baseline_threshold: Optional manual baseline threshold.
                              If None, baseline is estimated from data distribution
            block_threshold_factor: Multiplier for block detection threshold.
                                  Higher values = more conservative detection
            min_block_duration: Minimum duration for a block event (seconds)
        
        Returns:
            List of block event dictionaries, each containing:
            - start_time: Block start time (seconds)
            - end_time: Block end time (seconds)
            - duration: Block duration (seconds)
            - start_idx: Start index in data array
            - end_idx: End index in data array
            - average_amplitude: Mean current during block
            - baseline_amplitude: Estimated baseline (open channel) level
            - block_depth: Difference between baseline and block amplitude
        """
        if len(data) == 0 or len(time) == 0:
            return []
        
        # Estimate baseline (open channel level)
        if baseline_threshold is None:
            # Use histogram to find the most common (open) level
            hist, bin_edges = np.histogram(data, bins=100)
            max_bin_idx = np.argmax(hist)
            baseline_amplitude = (bin_edges[max_bin_idx] + bin_edges[max_bin_idx + 1]) / 2
            
            # Alternative: use median or mean of upper portion
            # Sort data and take median of upper half
            sorted_data = np.sort(data)
            upper_half = sorted_data[len(sorted_data)//2:]
            baseline_amplitude = np.median(upper_half)
        else:
            baseline_amplitude = baseline_threshold
        
        # Calculate standard deviation of baseline region
        # Use data points near baseline for std calculation
        baseline_mask = np.abs(data - baseline_amplitude) < (np.std(data) * 1.5)
        if np.sum(baseline_mask) < 10:
            # Fallback: use overall std
            baseline_std = np.std(data)
        else:
            baseline_std = np.std(data[baseline_mask])
        
        # Block detection: blocks move toward 0 from baseline
        # If baseline is negative, blocks are between baseline and 0 (closer to 0)
        # If baseline is positive, blocks are between baseline and 0 (closer to 0)
        
        # Determine block region based on baseline sign
        if baseline_amplitude < 0:
            # Negative baseline: blocks are between baseline and 0 (less negative)
            # Block threshold is closer to 0 than baseline
            block_threshold = baseline_amplitude + (block_threshold_factor * baseline_std)
            # But block must still be between baseline and 0
            block_threshold = min(block_threshold, 0.0)
            # Detect points that are between baseline and threshold (closer to 0)
            in_block = (data > block_threshold) & (data < 0) & (np.abs(data) < np.abs(baseline_amplitude))
        elif baseline_amplitude > 0:
            # Positive baseline: blocks are between baseline and 0 (less positive)
            # Block threshold is closer to 0 than baseline
            block_threshold = baseline_amplitude - (block_threshold_factor * baseline_std)
            # But block must still be between baseline and 0
            block_threshold = max(block_threshold, 0.0)
            # Detect points that are between threshold and baseline (closer to 0)
            in_block = (data < block_threshold) & (data > 0) & (np.abs(data) < np.abs(baseline_amplitude))
        else:
            # Baseline is exactly 0 - shouldn't happen, but handle gracefully
            # In this case, look for small deviations
            block_threshold = block_threshold_factor * baseline_std
            in_block = np.abs(data) < block_threshold
        
        # Find transitions into and out of blocks
        diff = np.diff(in_block.astype(int))
        block_starts = np.where(diff == 1)[0] + 1  # +1 because diff shifts indices
        block_ends = np.where(diff == -1)[0] + 1
        
        # Handle edge cases
        if in_block[0]:
            block_starts = np.concatenate([[0], block_starts])
        if in_block[-1]:
            block_ends = np.concatenate([block_ends, [len(data) - 1]])
        
        # Ensure we have matching starts and ends
        if len(block_starts) > len(block_ends):
            block_ends = np.concatenate([block_ends, [len(data) - 1]])
        if len(block_ends) > len(block_starts):
            block_starts = np.concatenate([[0], block_starts])
        
        # Convert min_block_duration to samples
        sample_rate = len(time) / (time[-1] - time[0]) if len(time) > 1 else 1
        min_block_samples = int(min_block_duration * sample_rate)
        
        # Process each detected block
        blocks = []
        for start_idx, end_idx in zip(block_starts, block_ends):
            if end_idx - start_idx < min_block_samples:
                continue
            
            block_data = data[start_idx:end_idx+1]
            block_time = time[start_idx:end_idx+1]
            
            # Calculate block properties
            start_time = time[start_idx]
            end_time = time[end_idx]
            duration = end_time - start_time
            average_amplitude = np.mean(block_data)
            # Block depth: how much closer to 0 than baseline
            block_depth = abs(baseline_amplitude) - abs(average_amplitude)
            
            blocks.append({
                'start_time': start_time,
                'end_time': end_time,
                'duration': duration,
                'start_idx': int(start_idx),
                'end_idx': int(end_idx),
                'average_amplitude': average_amplitude,
                'baseline_amplitude': baseline_amplitude,
                'block_depth': block_depth
            })
        
        return blocks
    
    @staticmethod
    def detect_blocks_multiple_sweeps(sweep_data_list: List,
                                     baseline_threshold: float = None,
                                     block_threshold_factor: float = 3.0,
                                     min_block_duration: float = 0.001) -> List[Dict]:
        """
        Detect block events across multiple sweeps
        
        Args:
            sweep_data_list: List of SweepData objects
            baseline_threshold: Optional manual baseline threshold
            block_threshold_factor: Factor for block detection
            min_block_duration: Minimum duration for a block event (seconds)
        
        Returns:
            List of all block events from all sweeps with sweep number included
        """
        all_blocks = []
        
        for sweep in sweep_data_list:
            blocks = BlockDetector.detect_blocks(
                sweep.data,
                sweep.time,
                baseline_threshold=baseline_threshold,
                block_threshold_factor=block_threshold_factor,
                min_block_duration=min_block_duration
            )
            
            # Add sweep information to each block
            for block in blocks:
                block['sweep_number'] = sweep.sweep_number
                block['channel'] = sweep.channel
                all_blocks.append(block)
        
        return all_blocks
    
    @staticmethod
    def detect_inserts(sweep_data_list: List,
                      baseline_start: float = 0.0,
                      baseline_end: float = 0.1,
                      response_start: float = 0.1,
                      response_end: float = 0.2,
                      threshold_factor: float = 3.0) -> List[Dict]:
        """
        Detect inserts/responses based on baseline vs response comparison
        
        Args:
            sweep_data_list: List of SweepData objects
            baseline_start: Start time for baseline window (fraction of sweep)
            baseline_end: End time for baseline window (fraction of sweep)
            response_start: Start time for response window (fraction of sweep)
            response_end: End time for response window (fraction of sweep)
            threshold_factor: Factor for threshold (e.g., 3 = 3x baseline std)
        
        Returns:
            List of insert dictionaries with sweep indices
        """
        if len(sweep_data_list) == 0:
            return []
        
        inserts = []
        
        for i, sweep in enumerate(sweep_data_list):
            # Calculate indices for windows
            baseline_start_idx = int(baseline_start * len(sweep.data))
            baseline_end_idx = int(baseline_end * len(sweep.data))
            response_start_idx = int(response_start * len(sweep.data))
            response_end_idx = int(response_end * len(sweep.data))
            
            # Ensure valid indices
            baseline_start_idx = max(0, baseline_start_idx)
            baseline_end_idx = min(len(sweep.data), baseline_end_idx)
            response_start_idx = max(0, response_start_idx)
            response_end_idx = min(len(sweep.data), response_end_idx)
            
            if baseline_end_idx <= baseline_start_idx or response_end_idx <= response_start_idx:
                continue
            
            # Calculate baseline statistics
            baseline_data = sweep.data[baseline_start_idx:baseline_end_idx]
            baseline_mean = np.mean(baseline_data)
            baseline_std = np.std(baseline_data)
            
            # Calculate response statistics
            response_data = sweep.data[response_start_idx:response_end_idx]
            response_mean = np.mean(response_data)
            response_max = np.max(response_data)
            response_min = np.min(response_data)
            
            # Detect if response deviates significantly from baseline
            threshold = abs(baseline_mean) + (threshold_factor * baseline_std)
            deviation = max(abs(response_max - baseline_mean), 
                          abs(response_min - baseline_mean))
            
            if deviation > threshold:
                inserts.append({
                    'sweep': i,
                    'baseline_mean': baseline_mean,
                    'baseline_std': baseline_std,
                    'response_mean': response_mean,
                    'response_max': response_max,
                    'response_min': response_min,
                    'deviation': deviation
                })
        
        return inserts

