#!/usr/bin/env python3
import os
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import subprocess
import threading
import re
from datetime import timedelta
import time
import queue

# Conditionally import tkmacosx for MacOS-specific buttons
if sys.platform == 'darwin':
    try:
        from tkmacosx import Button
        USE_MACOS_BUTTONS = True
    except ImportError:
        USE_MACOS_BUTTONS = False
else:
    USE_MACOS_BUTTONS = False

class VideoCompressorApp:
    """
    A GUI application that compresses video files using ffmpeg.
    Features:
    - Select input directory containing video files
    - Select output directory for compressed videos
    - Choose output format, quality (CRF), and resolution
    - Show progress for overall batch and current file
    - Show estimated time remaining
    """
    
    # Common video file extensions
    VIDEO_EXTENSIONS = ['.mp4', '.mov', '.avi', '.mkv', '.wmv', '.flv', '.webm', '.m4v', '.3gp']
    
    # Available output formats
    OUTPUT_FORMATS = ['mp4', 'mkv', 'webm']
    
    # Preset quality levels (CRF values - lower is better quality but larger file)
    QUALITY_LEVELS = {
        'High (larger file)': '18',
        'Medium': '23',
        'Low (smaller file)': '28',
        'Custom': 'custom'
    }
    
    # Common resolutions
    RESOLUTIONS = [
        'Original',
        '4K (3840x2160)',
        '1080p (1920x1080)',
        '720p (1280x720)',
        '480p (854x480)'
    ]
    
    def __init__(self, root):
        """Initialize the application."""
        self.root = root
        self.root.title("Video Compressor")
        self.root.geometry("800x600")
        self.root.minsize(650, 500)
        
        # Set MacOS specific appearance if available
        self.use_macos_buttons = USE_MACOS_BUTTONS
        
        # Application state
        self.input_dir = tk.StringVar()
        self.output_dir = tk.StringVar()
        self.output_format = tk.StringVar(value=self.OUTPUT_FORMATS[0])
        self.quality_preset = tk.StringVar(value=list(self.QUALITY_LEVELS.keys())[1])  # Medium by default
        self.custom_crf = tk.StringVar(value='23')
        self.resolution = tk.StringVar(value=self.RESOLUTIONS[0])  # Original by default
        self.current_file_var = tk.StringVar(value="No file processing")
        self.progress_text = tk.StringVar(value="0/0 files processed")
        self.time_remaining = tk.StringVar(value="--:--:--")
        self.status_var = tk.StringVar(value="Ready")
        
        self.is_processing = False
        self.cancel_requested = False
        self.video_files = []
        
        # Thread for background processing
        self.process_thread = None
        
        # Queue for thread-safe UI updates
        self.update_queue = queue.Queue()
        
        # Check if ffmpeg is available
        self.check_ffmpeg()
        
        # Start the update checker
        self.check_update_queue()
        
        # Create UI elements
        self.create_widgets()
        
        # Update the state of controls based on initial values
        self.update_quality_controls()
        
        # Center the window on screen
        self.center_window()
        
    def center_window(self):
        """Center the application window on the screen."""
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f'{width}x{height}+{x}+{y}')
    
    def check_ffmpeg(self):
        """Check if ffmpeg is installed and available in the system path."""
        try:
            # Check for ffmpeg
            subprocess.check_output(['ffmpeg', '-version'], stderr=subprocess.STDOUT)
            # Check for ffprobe
            subprocess.check_output(['ffprobe', '-version'], stderr=subprocess.STDOUT)
            return True
        except (subprocess.SubprocessError, FileNotFoundError):
            messagebox.showerror(
                "FFmpeg Not Found", 
                "FFmpeg and/or ffprobe could not be found. Please install FFmpeg and ensure it's in your system PATH."
            )
            self.start_button.configure(state=tk.DISABLED)
            return False
    
    def update_ui_state(self, processing):
        """Update UI elements based on processing state."""
        state = tk.DISABLED if processing else tk.NORMAL
        
        # Update UI controls
        for widget in [self.start_button]:
            widget.configure(state=tk.DISABLED if processing else tk.NORMAL)
            
        for widget in [self.cancel_button]:
            widget.configure(state=tk.NORMAL if processing else tk.DISABLED)
        
        # Reset progress if we're starting
        if not processing:
            self.file_progress['value'] = 0
            self.overall_progress['value'] = 0
            self.current_file_var.set("No file processing")
            self.progress_text.set("0/0 files processed")
            self.time_remaining.set("--:--:--")
            self.status_var.set("Ready")
    
    def check_update_queue(self):
        """Check for and process any pending UI updates."""
        try:
            while True:
                try:
                    update_type, data = self.update_queue.get_nowait()
                    
                    if update_type == 'ui_state':
                        self.update_ui_state(data)
                    elif update_type == 'label':
                        var, text = data
                        var.set(text)
                    elif update_type == 'progress':
                        progress_bar, value = data
                        progress_bar['value'] = value
                    elif update_type == 'message':
                        title, message = data
                        messagebox.showerror(title, message)
                    
                    self.update_queue.task_done()
                except queue.Empty:
                    break
        finally:
            # Schedule the next check
            self.root.after(100, self.check_update_queue)
    
    def safe_update_label(self, var, text):
        """Thread-safe method to update label text"""
        if threading.current_thread() is threading.main_thread():
            var.set(text)
        else:
            self.update_queue.put(('label', (var, text)))
    
    def safe_update_progress(self, progress_bar, value):
        """Thread-safe method to update progress bar"""
        if threading.current_thread() is threading.main_thread():
            progress_bar['value'] = value
        else:
            self.update_queue.put(('progress', (progress_bar, value)))
    
    def create_widgets(self):
        """Create and arrange the UI elements."""
        # Main frame with some padding
        main_frame = ttk.Frame(self.root, padding="20 20 20 20")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Directory selection frame
        dir_frame = ttk.LabelFrame(main_frame, text="Directory Selection", padding="10 10 10 10")
        dir_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Input directory row
        ttk.Label(dir_frame, text="Input Directory:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        ttk.Entry(dir_frame, textvariable=self.input_dir, width=50).grid(row=0, column=1, sticky=tk.EW, padx=5, pady=5)
        browse_input_btn = ttk.Button(dir_frame, text="Browse...", command=self.browse_input_dir)
        browse_input_btn.grid(row=0, column=2, padx=5, pady=5)
        
        # Output directory row
        ttk.Label(dir_frame, text="Output Directory:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        ttk.Entry(dir_frame, textvariable=self.output_dir, width=50).grid(row=1, column=1, sticky=tk.EW, padx=5, pady=5)
        browse_output_btn = ttk.Button(dir_frame, text="Browse...", command=self.browse_output_dir)
        browse_output_btn.grid(row=1, column=2, padx=5, pady=5)
        
        dir_frame.columnconfigure(1, weight=1)
        
        # Compression settings frame
        settings_frame = ttk.LabelFrame(main_frame, text="Compression Settings", padding="10 10 10 10")
        settings_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Format row
        ttk.Label(settings_frame, text="Output Format:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        format_combo = ttk.Combobox(settings_frame, textvariable=self.output_format, values=self.OUTPUT_FORMATS, width=10)
        format_combo.grid(row=0, column=1, sticky=tk.W, padx=5, pady=5)
        format_combo.config(state="readonly")
        
        # Quality row
        ttk.Label(settings_frame, text="Quality:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        quality_combo = ttk.Combobox(settings_frame, textvariable=self.quality_preset, 
                                    values=list(self.QUALITY_LEVELS.keys()), width=15)
        quality_combo.grid(row=1, column=1, sticky=tk.W, padx=5, pady=5)
        quality_combo.config(state="readonly")
        quality_combo.bind("<<ComboboxSelected>>", lambda event: self.update_quality_controls())
        
        # Custom CRF value
        ttk.Label(settings_frame, text="Custom CRF:").grid(row=1, column=2, sticky=tk.W, padx=5, pady=5)
        self.crf_entry = ttk.Entry(settings_frame, textvariable=self.custom_crf, width=5)
        self.crf_entry.grid(row=1, column=3, sticky=tk.W, padx=5, pady=5)
        ttk.Label(settings_frame, text="(0-51, lower is better quality)").grid(
            row=1, column=4, sticky=tk.W, padx=5, pady=5)
        
        # Resolution row
        ttk.Label(settings_frame, text="Resolution:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=5)
        resolution_combo = ttk.Combobox(settings_frame, textvariable=self.resolution, 
                                      values=self.RESOLUTIONS, width=15)
        resolution_combo.grid(row=2, column=1, sticky=tk.W, padx=5, pady=5)
        resolution_combo.config(state="readonly")
        
        # Progress frame
        progress_frame = ttk.LabelFrame(main_frame, text="Progress", padding="10 10 10 10")
        progress_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Current file progress
        ttk.Label(progress_frame, text="Current File:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        ttk.Label(progress_frame, textvariable=self.current_file_var).grid(row=0, column=1, sticky=tk.W, padx=5, pady=5)
        
        # Current file progress bar
        self.file_progress = ttk.Progressbar(progress_frame, orient=tk.HORIZONTAL, length=100, mode='determinate')
        self.file_progress.grid(row=1, column=0, columnspan=2, sticky=tk.EW, padx=5, pady=5)
        
        # Overall progress
        ttk.Label(progress_frame, text="Overall Progress:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=5)
        ttk.Label(progress_frame, textvariable=self.progress_text).grid(row=2, column=1, sticky=tk.W, padx=5, pady=5)
        
        # Overall progress bar
        self.overall_progress = ttk.Progressbar(progress_frame, orient=tk.HORIZONTAL, length=100, mode='determinate')
        self.overall_progress.grid(row=3, column=0, columnspan=2, sticky=tk.EW, padx=5, pady=5)
        
        # Estimated time remaining
        ttk.Label(progress_frame, text="Est. Time Remaining:").grid(row=4, column=0, sticky=tk.W, padx=5, pady=5)
        ttk.Label(progress_frame, textvariable=self.time_remaining).grid(row=4, column=1, sticky=tk.W, padx=5, pady=5)
        
        # Status message
        ttk.Label(progress_frame, textvariable=self.status_var, font=('Helvetica', 10, 'italic')).grid(
            row=5, column=0, columnspan=2, sticky=tk.W, padx=5, pady=5)
        
        progress_frame.columnconfigure(1, weight=1)
        
        # Buttons frame
        buttons_frame = ttk.Frame(main_frame)
        buttons_frame.pack(fill=tk.X, padx=5, pady=10)
        
        # Start and Cancel buttons
        if self.use_macos_buttons:
            from tkmacosx import Button
            self.start_button = Button(buttons_frame, text="Start Compression", command=self.start_compression, 
                                     fg='white', bg='#0078D7', borderless=True, width=150, height=30)
            self.start_button.pack(side=tk.RIGHT, padx=5)
            
            self.cancel_button = Button(buttons_frame, text="Cancel", command=self.cancel_compression,
                                      fg='black', bg='#E1E1E1', borderless=True, width=100, height=30)
            self.cancel_button.pack(side=tk.RIGHT, padx=5)
            self.cancel_button.configure(state=tk.DISABLED)
        else:
            self.start_button = ttk.Button(buttons_frame, text="Start Compression", command=self.start_compression)
            self.start_button.pack(side=tk.RIGHT, padx=5)
            
            self.cancel_button = ttk.Button(buttons_frame, text="Cancel", command=self.cancel_compression)
            self.cancel_button.pack(side=tk.RIGHT, padx=5)
            self.cancel_button.configure(state=tk.DISABLED)
            
    def browse_input_dir(self):
        """Open a directory dialog to select the input directory."""
        directory = filedialog.askdirectory(title="Select Input Directory")
        if directory:
            self.input_dir.set(directory)
            # Auto-suggest output directory
            if not self.output_dir.get():
                suggested_output = os.path.join(os.path.dirname(directory), 
                                               os.path.basename(directory) + "_compressed")
                self.output_dir.set(suggested_output)

    def browse_output_dir(self):
        """Open a directory dialog to select the output directory."""
        directory = filedialog.askdirectory(title="Select Output Directory")
        if directory:
            self.output_dir.set(directory)
            
    def update_quality_controls(self):
        """Enable/disable custom CRF entry based on quality preset selection."""
        if self.quality_preset.get() == 'Custom':
            self.crf_entry.configure(state=tk.NORMAL)
        else:
            self.crf_entry.configure(state=tk.DISABLED)
            # Update custom CRF value with the current preset's value
            preset = self.quality_preset.get()
            if preset in self.QUALITY_LEVELS:
                self.custom_crf.set(self.QUALITY_LEVELS[preset])
    
    def validate_inputs(self):
        """Validate user inputs before starting compression."""
        # Check input directory
        input_dir = self.input_dir.get()
        if not input_dir or not os.path.isdir(input_dir):
            messagebox.showerror("Error", "Please select a valid input directory.")
            return False
            
        # Check output directory
        output_dir = self.output_dir.get()
        if not output_dir:
            messagebox.showerror("Error", "Please select an output directory.")
            return False
            
        # Create output directory if it doesn't exist
        if not os.path.exists(output_dir):
            try:
                os.makedirs(output_dir)
            except OSError as e:
                messagebox.showerror("Error", f"Failed to create output directory: {e}")
                return False
                
        # Find video files
        self.video_files = self.find_video_files(input_dir)
        if not self.video_files:
            messagebox.showerror("Error", "No video files found in the input directory.")
            return False
            
        # Validate quality settings
        if self.quality_preset.get() == 'Custom':
            try:
                crf_value = int(self.custom_crf.get())
                if not (0 <= crf_value <= 51):
                    messagebox.showerror("Error", "CRF value must be between 0 and 51.")
                    return False
            except ValueError:
                messagebox.showerror("Error", "CRF value must be a number between 0 and 51.")
                return False
                
        return True
    
    def find_video_files(self, directory):
        """Find all video files in the input directory."""
        video_files = []
        
        for root, _, files in os.walk(directory):
            for file in files:
                file_path = os.path.join(root, file)
                file_ext = os.path.splitext(file)[1].lower()
                if file_ext in self.VIDEO_EXTENSIONS:
                    video_files.append(file_path)
        
        return sorted(video_files)
    
    def get_ffmpeg_command(self, input_file, output_file):
        """Build the ffmpeg command based on user settings."""
        # Get quality settings
        if self.quality_preset.get() == 'Custom':
            crf = self.custom_crf.get()
        else:
            crf = self.QUALITY_LEVELS[self.quality_preset.get()]
        
        # Basic command
        cmd = ['ffmpeg', '-i', input_file, '-y']  # -y to overwrite without asking
        
        # Add resolution if not original
        if self.resolution.get() != 'Original':
            # Extract resolution from the format string
            match = re.search(r'(\d+x\d+)', self.resolution.get())
            if match:
                cmd.extend(['-vf', f'scale={match.group(1)}'])
        
        # Add format-specific encoding settings
        fmt = self.output_format.get()
        if fmt == 'mp4':
            cmd.extend(['-c:v', 'libx264', '-crf', crf, '-preset', 'medium'])
        elif fmt == 'webm':
            cmd.extend(['-c:v', 'libvpx-vp9', '-crf', crf, '-b:v', '0'])
        elif fmt == 'mkv':
            cmd.extend(['-c:v', 'libx264', '-crf', crf, '-preset', 'medium'])
        
        # Add audio codec settings
        cmd.extend(['-c:a', 'aac', '-b:a', '128k'])
        
        # Output file
        cmd.append(output_file)
        
        return cmd
    def start_compression(self):
        """Start the compression process."""
        if self.is_processing:
            return
            
        if not self.validate_inputs():
            return
            
        self.is_processing = True
        self.cancel_requested = False
        
        # Update UI
        self.update_ui_state(True)
        
        # Start compression in a background thread
        self.process_thread = threading.Thread(target=self.process_video_files)
        self.process_thread.daemon = True
        self.process_thread.start()
    def cancel_compression(self):
        """Cancel the compression process."""
        if not self.is_processing:
            return
            
        self.cancel_requested = True
        # Use thread-safe update for consistency
        self.safe_update_label(self.status_var, "Cancelling... (waiting for current file to finish)")
    def process_video_files(self):
        """Process all video files in the input directory."""
        total_files = len(self.video_files)
        processed_files = 0
        failed_files = 0
        
        start_time = time.time()
        avg_time_per_file = None
        
        try:
            for input_file in self.video_files:
                if self.cancel_requested:
                    break
                    
                # Determine output file path
                rel_path = os.path.relpath(input_file, self.input_dir.get())
                output_file = os.path.join(
                    self.output_dir.get(),
                    os.path.splitext(rel_path)[0] + '.' + self.output_format.get()
                )
                
                # Ensure output directory exists (for subdirectories)
                os.makedirs(os.path.dirname(output_file), exist_ok=True)
                
                # Update UI with current file
                filename = os.path.basename(input_file)
                self.current_file_var.set(filename)
                self.progress_text.set(f"{processed_files}/{total_files} files processed")
                self.status_var.set(f"Compressing: {filename}")
                self.file_progress['value'] = 0
                
                # Compress the video
                result = self.compress_video(input_file, output_file)
                
                if result:
                    processed_files += 1
                else:
                    failed_files += 1
                
                # Update overall progress
                self.overall_progress['value'] = (processed_files / total_files) * 100
                
                # Update average time and estimate remaining time
                if processed_files > 0:
                    elapsed_time = time.time() - start_time
                    avg_time_per_file = elapsed_time / processed_files
                    remaining_files = total_files - processed_files
                    est_time_remaining = avg_time_per_file * remaining_files
                    
                    # Format time remaining
                    time_str = str(timedelta(seconds=int(est_time_remaining)))
                    self.time_remaining.set(time_str)
            
            # Final update
            if self.cancel_requested:
                self.status_var.set("Compression cancelled.")
            else:
                self.progress_text.set(f"{processed_files}/{total_files} files processed")
                if failed_files > 0:
                    self.status_var.set(f"Compression completed with {failed_files} failures.")
                else:
                    self.status_var.set("Compression completed successfully!")
                self.time_remaining.set("00:00:00")
        
        except Exception as e:
            error_msg = f"Error: {str(e)}"
            self.safe_update_label(self.status_var, error_msg)
            # Queue the error message dialog for the main thread
            self.update_queue.put(('message', ("Error", f"An error occurred during compression: {str(e)}")))
        
        finally:
            self.is_processing = False
            # Use thread-safe update method
            if threading.current_thread() is threading.main_thread():
                self.update_ui_state(False)
            else:
                self.update_queue.put(('ui_state', False))
    def compress_video(self, input_file, output_file):
        """Compress a single video file using ffmpeg and track progress."""
        try:
            # Get video duration
            duration_cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', 
                          '-of', 'default=noprint_wrappers=1:nokey=1', input_file]
            duration_output = subprocess.check_output(duration_cmd, stderr=subprocess.STDOUT, universal_newlines=True)
            
            try:
                duration = float(duration_output.strip())
            except ValueError:
                duration = 0
            
            # Build and execute ffmpeg command
            cmd = self.get_ffmpeg_command(input_file, output_file)
            
            # Add progress monitoring parameters
            cmd.insert(1, '-progress')
            cmd.insert(2, 'pipe:1')
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                bufsize=1
            )
            
            # Process output to track progress
            current_time = 0
            while process.poll() is None:
                output_line = process.stdout.readline().strip()
                
                if output_line.startswith('out_time_ms='):
                    try:
                        # Convert microseconds to seconds
                        current_time = float(output_line.split('=')[1]) / 1000000
                        if duration > 0:
                            progress = min(100, (current_time / duration) * 100)
                            # Use thread-safe progress update
                            self.safe_update_progress(self.file_progress, progress)
                    except Exception:
                        # Ignore errors in progress parsing
                        pass
            
            # Check if process completed successfully
            if process.returncode != 0:
                error_output = process.stderr.read()
                self.safe_update_label(self.status_var, f"Error compressing {os.path.basename(input_file)}")
                print(f"ffmpeg error: {error_output}")
                return False
            
            # Set progress to 100% when complete
            self.safe_update_progress(self.file_progress, 100)
            return True
            
        except Exception as e:
            self.safe_update_label(self.status_var, f"Error: {str(e)}")
            print(f"Error compressing {input_file}: {str(e)}")
            return False

if __name__ == "__main__":
    root = tk.Tk()
    app = VideoCompressorApp(root)
    root.mainloop()