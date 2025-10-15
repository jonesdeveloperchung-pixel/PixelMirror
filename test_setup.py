#!/usr/bin/env python3
"""
Test script to verify PixelMirror setup and dependencies.
"""

import sys
import importlib

def test_imports():
    """Test if all required modules can be imported."""
    required_modules = [
        'websockets',
        'PIL',
        'numpy',
        'pyautogui',
        'tkinter'
    ]
    
    print("Testing imports...")
    failed_imports = []
    
    for module in required_modules:
        try:
            importlib.import_module(module)
            print(f"✅ {module}")
        except ImportError as e:
            print(f"❌ {module}: {e}")
            failed_imports.append(module)
    
    if failed_imports:
        print(f"\n❌ Failed to import: {', '.join(failed_imports)}")
        print("Please install missing dependencies with: pip install -r requirements.txt")
        return False
    else:
        print("\n✅ All dependencies are available!")
        return True

def test_pyautogui():
    """Test pyautogui functionality."""
    try:
        import pyautogui
        # Disable failsafe for testing
        pyautogui.FAILSAFE = False
        
        # Test screen size detection
        screen_size = pyautogui.size()
        print(f"✅ Screen size detected: {screen_size}")
        
        # Test screenshot capability
        screenshot = pyautogui.screenshot()
        print(f"✅ Screenshot captured: {screenshot.size}")
        
        return True
    except Exception as e:
        print(f"❌ PyAutoGUI test failed: {e}")
        return False

def test_tkinter():
    """Test tkinter functionality."""
    try:
        import tkinter as tk
        # Create a test window (don't show it)
        root = tk.Tk()
        root.withdraw()  # Hide the window
        root.destroy()
        print("✅ Tkinter is working")
        return True
    except Exception as e:
        print(f"❌ Tkinter test failed: {e}")
        return False

def main():
    print("PixelMirror Setup Test")
    print("=" * 30)
    
    all_tests_passed = True
    
    # Test imports
    if not test_imports():
        all_tests_passed = False
    
    print("\nTesting functionality...")
    
    # Test pyautogui
    if not test_pyautogui():
        all_tests_passed = False
    
    # Test tkinter
    if not test_tkinter():
        all_tests_passed = False
    
    print("\n" + "=" * 30)
    if all_tests_passed:
        print("✅ All tests passed! PixelMirror is ready to use.")
        print("\nTo start the server: python pixelmirror.py --mode server")
        print("To start the client: python pixelmirror.py --mode client")
    else:
        print("❌ Some tests failed. Please fix the issues above.")
        sys.exit(1)

if __name__ == "__main__":
    main()