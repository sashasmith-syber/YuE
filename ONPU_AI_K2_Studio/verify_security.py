#!/usr/bin/env python3
"""
Quick verification that security layer is working
"""
import sys
sys.path.insert(0, 'security-layer')
from persistence import SecurityPersistence
import tempfile, os

# Test persistence
temp = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
temp.close()
p = SecurityPersistence(temp.name)

# Brute force simulation
print("Testing brute force protection...")
for i in range(11):
    count = p.record_auth_failure('10.0.0.1')
    if i < 10:
        status = "allowed"
    else:
        status = "BLOCKED"
    print(f'  Attempt {i+1}: count={count} ({status})')

blocked = p.is_ip_blocked('10.0.0.1')
print(f'\nResult: IP blocked = {blocked}')

if blocked:
    print('\n✅ SECURITY LAYER ACTIVE - Brute force protection working!')
else:
    print('\n❌ SECURITY LAYER ERROR - IP should be blocked!')

os.unlink(temp.name)
