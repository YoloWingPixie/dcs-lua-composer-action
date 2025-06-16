-- Test Library v1.0
-- A small test library for unit testing

TestLib = {}

function TestLib.greet(name)
    return "Hello, " .. name .. " from TestLib!"
end

function TestLib.add(a, b)
    return a + b
end

return TestLib
