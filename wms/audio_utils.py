"""Audio utilities for text-to-speech functionality in the WMS application."""

import streamlit.components.v1 as components


def play_last_4_digits(text: str, enabled: bool = True) -> None:
    """Play audio of the last 4 characters (up to 4) of the scanned text using Web Speech API.
    
    Args:
        text: The scanned text (SKU or other identifier)
        enabled: Whether audio is enabled (from session state)
    """
    if not enabled or not text:
        return
    
    # Get last 4 characters (or less if text is shorter)
    last_4 = text[-4:] if len(text) >= 4 else text
    
    # Add a unique timestamp to force the component to re-render each time
    import time
    timestamp = int(time.time() * 1000)
    
    # Create JavaScript to speak the digits using Web Speech API
    # Use a small delay to ensure it doesn't interfere with Streamlit's rerun cycle
    js_code = f"""
    <script>
    (function() {{
        // Unique ID to force execution: {timestamp}
        // Only proceed if Web Speech API is available
        if ('speechSynthesis' in window) {{
            // Small delay to avoid interfering with Streamlit reruns
            setTimeout(function() {{
                const utterance = new SpeechSynthesisUtterance('{last_4}');
                utterance.rate = 0.8;  // Slightly slower for clarity
                utterance.pitch = 1.0;
                utterance.volume = 1.0;
                
                // Speak each digit separately for better clarity
                const digits = '{last_4}'.split('').join(' ');
                utterance.text = digits;
                
                window.speechSynthesis.cancel();  // Cancel any ongoing speech
                window.speechSynthesis.speak(utterance);
            }}, 100);
        }}
    }})();
    </script>
    """
    
    components.html(js_code, height=0)


def create_audio_toggle_js() -> str:
    """Create JavaScript code to handle audio toggle state.
    
    Returns:
        JavaScript code as a string
    """
    return """
    <script>
    (function() {
        // Store audio state in sessionStorage
        window.enableAudio = function(enabled) {
            sessionStorage.setItem('wms_audio_enabled', enabled ? 'true' : 'false');
        };
        
        window.isAudioEnabled = function() {
            return sessionStorage.getItem('wms_audio_enabled') === 'true';
        };
    })();
    </script>
    """
