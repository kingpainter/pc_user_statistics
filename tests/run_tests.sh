#!/bin/bash
# Test runner script for PC User Statistics integration

set -e

echo "🧪 Running PC User Statistics Tests"
echo "===================================="
echo ""

# Check if pytest is installed
if ! command -v pytest &> /dev/null; then
    echo "❌ pytest not found. Installing test requirements..."
    pip install -r requirements_test.txt
fi

echo "📋 Running unit tests..."
pytest tests/test_helpers.py -v

echo ""
echo "🔧 Running integration tests..."
pytest tests/test_init.py -v

echo ""
echo "📊 Generating coverage report..."
pytest --cov=custom_components.pc_user_statistics \
       --cov-report=term-missing \
       --cov-report=html \
       tests/

echo ""
echo "✅ All tests completed!"
echo ""
echo "📈 Coverage report saved to htmlcov/index.html"
echo "   Open it in your browser to view detailed coverage"