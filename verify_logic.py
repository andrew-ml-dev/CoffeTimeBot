import database
import os

TEST_DB = 'test_coffee_bot.db'

# Monkey patch database name for testing
database.DB_NAME = TEST_DB

# Ensure clean slate
if os.path.exists(TEST_DB):
    os.remove(TEST_DB)

database.init_db()

# Test 1: Add users
print("Test 1: Adding users...")
database.add_user(1, "Alice")
database.add_user(2, "Bob")
users = database.get_all_users()
assert len(users) == 2
print("Passed.")

# Test 2: Set desire
print("Test 2: Setting desire...")
database.set_desire(1, 10)
users = database.get_all_users()
alice = next(u for u in users if u['user_id'] == 1)
bob = next(u for u in users if u['user_id'] == 2)
assert alice['desire'] == 10
assert bob['desire'] == 0
print("Passed.")

# Test 3: Threshold Logic
print("Test 3: Checking Threshold Logic...")
DESIRE_THRESHOLD = 7

# Only Alice is ready
ready_users = [u for u in users if u['desire'] >= DESIRE_THRESHOLD]
assert len(ready_users) == 1
assert len(ready_users) != len(users)

# Bob gets ready
database.set_desire(2, 8)
users = database.get_all_users()
ready_users = [u for u in users if u['desire'] >= DESIRE_THRESHOLD]
assert len(ready_users) == 2
assert len(ready_users) == len(users)
print("Passed. All users ready logic works.")

# Test 4: Reset
print("Test 4: Resetting desires...")
database.reset_desires()
users = database.get_all_users()
assert all(u['desire'] == 0 for u in users)
print("Passed.")

print("\nALL SYSTEM CHECKS PASSED.")

# Cleanup
if os.path.exists(TEST_DB):
    os.remove(TEST_DB)
