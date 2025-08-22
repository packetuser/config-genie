#!/usr/bin/env python3
"""Simple test runner for Config-Genie."""

import sys
import traceback
from pathlib import Path

# Add source directory to Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

def run_test_module(module_name):
    """Run tests from a specific module."""
    try:
        print(f"\n{'='*50}")
        print(f"Running tests from {module_name}")
        print('='*50)
        
        module = __import__(f"tests.{module_name}", fromlist=[''])
        
        # Find test classes and methods
        test_count = 0
        passed = 0
        failed = 0
        
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (isinstance(attr, type) and 
                attr_name.startswith('Test') and 
                attr != type):
                
                test_class = attr()
                
                for method_name in dir(test_class):
                    if method_name.startswith('test_'):
                        test_count += 1
                        test_method = getattr(test_class, method_name)
                        
                        try:
                            print(f"  Running {attr_name}.{method_name}...", end=" ")
                            test_method()
                            print("PASS")
                            passed += 1
                        except Exception as e:
                            print(f"FAIL - {str(e)}")
                            if "--verbose" in sys.argv:
                                traceback.print_exc()
                            failed += 1
        
        print(f"\nResults for {module_name}: {passed} passed, {failed} failed, {test_count} total")
        return passed, failed, test_count
    
    except ImportError as e:
        print(f"Failed to import {module_name}: {e}")
        return 0, 0, 0
    except Exception as e:
        print(f"Error running tests in {module_name}: {e}")
        if "--verbose" in sys.argv:
            traceback.print_exc()
        return 0, 0, 0

def main():
    """Run all tests."""
    print("Config-Genie Test Suite")
    print("="*50)
    
    # Test modules to run
    test_modules = [
        'test_cli',
        'test_inventory', 
        'test_templates',
        'test_connector',
        'test_validation',
        'test_logging',
        'test_integration'
    ]
    
    total_passed = 0
    total_failed = 0
    total_tests = 0
    
    for module_name in test_modules:
        passed, failed, count = run_test_module(module_name)
        total_passed += passed
        total_failed += failed
        total_tests += count
    
    # Summary
    print(f"\n{'='*50}")
    print("FINAL SUMMARY")
    print('='*50)
    print(f"Total tests: {total_tests}")
    print(f"Passed: {total_passed}")
    print(f"Failed: {total_failed}")
    
    if total_failed == 0:
        print("\n🎉 All tests passed!")
        return 0
    else:
        print(f"\n❌ {total_failed} tests failed")
        return 1

if __name__ == "__main__":
    sys.exit(main())