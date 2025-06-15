#!/bin/bash
# Integration tests for .composerrc and action input merging

set -e

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Test directory
TEST_DIR=$(mktemp -d)
trap "rm -rf $TEST_DIR" EXIT

# Save the script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Helper functions
pass() {
    echo -e "${GREEN}✓ $1${NC}"
}

fail() {
    echo -e "${RED}✗ $1${NC}"
    exit 1
}

# Simulate the merging logic from action.yml
select_value() {
    local input_value="$1"
    local rc_value="$2"
    local default_value="$3"
    
    if [ -n "$input_value" ] && [ "$input_value" != "$default_value" ]; then
        echo "$input_value"
    elif [ -n "$rc_value" ]; then
        echo "$rc_value"
    else
        echo "$default_value"
    fi
}

echo "Testing configuration merging scenarios..."

# Test 1: Action inputs take priority over .composerrc
echo -n "Test 1: Action inputs override .composerrc values... "
ACTION_INPUT="custom_action_value"
RC_VALUE="rc_value"
DEFAULT="default_value"
RESULT=$(select_value "$ACTION_INPUT" "$RC_VALUE" "$DEFAULT")
if [ "$RESULT" = "$ACTION_INPUT" ]; then
    pass "Action input takes priority"
else
    fail "Expected '$ACTION_INPUT', got '$RESULT'"
fi

# Test 2: .composerrc values used when action input is empty
echo -n "Test 2: .composerrc values used when action input empty... "
ACTION_INPUT=""
RC_VALUE="rc_value"
DEFAULT="default_value"
RESULT=$(select_value "$ACTION_INPUT" "$RC_VALUE" "$DEFAULT")
if [ "$RESULT" = "$RC_VALUE" ]; then
    pass ".composerrc value used"
else
    fail "Expected '$RC_VALUE', got '$RESULT'"
fi

# Test 3: Default values used when both are empty
echo -n "Test 3: Default values used when both are empty... "
ACTION_INPUT=""
RC_VALUE=""
DEFAULT="default_value"
RESULT=$(select_value "$ACTION_INPUT" "$RC_VALUE" "$DEFAULT")
if [ "$RESULT" = "$DEFAULT" ]; then
    pass "Default value used"
else
    fail "Expected '$DEFAULT', got '$RESULT'"
fi

# Test 4: Action input same as default doesn't override .composerrc
echo -n "Test 4: Action input matching default doesn't override .composerrc... "
ACTION_INPUT="default_value"
RC_VALUE="rc_value"
DEFAULT="default_value"
RESULT=$(select_value "$ACTION_INPUT" "$RC_VALUE" "$DEFAULT")
if [ "$RESULT" = "$RC_VALUE" ]; then
    pass ".composerrc value preferred over default action input"
else
    fail "Expected '$RC_VALUE', got '$RESULT'"
fi

# Test 5: Complete .composerrc scenario
echo -n "Test 5: Complete .composerrc file scenario... "
cd "$TEST_DIR"
cat > .composerrc <<EOF
{
    "source_directory": "my_src",
    "output_file": "my_dist/output.lua",
    "namespace_file": "my_namespace.lua",
    "entrypoint_file": "my_main.lua",
    "dcs_strict_sanitize": false
}
EOF

# Simulate reading .composerrc
export GITHUB_OUTPUT="$TEST_DIR/github_output"
python3 "$SCRIPT_DIR/read_composerrc.py" "$TEST_DIR" > /dev/null 2>&1

# Check outputs
if grep -q "rc_source_directory=my_src" "$GITHUB_OUTPUT" && \
   grep -q "rc_output_file=my_dist/output.lua" "$GITHUB_OUTPUT" && \
   grep -q "rc_namespace_file=my_namespace.lua" "$GITHUB_OUTPUT" && \
   grep -q "rc_entrypoint_file=my_main.lua" "$GITHUB_OUTPUT" && \
   grep -q "rc_dcs_strict_sanitize=false" "$GITHUB_OUTPUT"; then
    pass "Complete .composerrc parsed correctly"
else
    fail "Failed to parse complete .composerrc"
fi

# Test 6: Incomplete .composerrc scenario
echo -n "Test 6: Incomplete .composerrc file scenario... "
cd "$TEST_DIR"
rm -f "$GITHUB_OUTPUT"
cat > .composerrc <<EOF
{
    "namespace_file": "partial_namespace.lua",
    "entrypoint_file": "partial_main.lua"
}
EOF

# Simulate reading .composerrc
export GITHUB_OUTPUT="$TEST_DIR/github_output2"
python3 "$SCRIPT_DIR/read_composerrc.py" "$TEST_DIR" || echo "Python script failed with exit code $?"

# Check outputs - should only have the specified values
if [ -f "$GITHUB_OUTPUT" ]; then
    if grep -q "rc_namespace_file=partial_namespace.lua" "$GITHUB_OUTPUT" && \
       grep -q "rc_entrypoint_file=partial_main.lua" "$GITHUB_OUTPUT" && \
       ! grep -q "rc_source_directory" "$GITHUB_OUTPUT" && \
       ! grep -q "rc_output_file" "$GITHUB_OUTPUT"; then
        pass "Incomplete .composerrc parsed correctly"
    else
        echo "Debug: Contents of $GITHUB_OUTPUT:"
        cat "$GITHUB_OUTPUT"
        fail "Failed to parse incomplete .composerrc correctly"
    fi
else
    fail "GitHub output file not created"
fi

echo -e "\n${GREEN}All tests passed!${NC}"