
-- External Dependency: test-lib
-- Description: Small test library for integration testing
-- Source: external_deps/test_lib.lua
-- License:
-- MIT License
--
-- Copyright (c) 2024 Test Library
--
-- Permission is hereby granted, free of charge, to any person obtaining a copy
-- of this software and associated documentation files (the "Software"), to deal
-- in the Software without restriction.

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

-- Combined and Sanitized Lua script generated on 2025-06-18T20:28:00.859144+00:00
-- THIS IS A RELEASE FILE. DO NOT EDIT THIS FILE DIRECTLY. EDIT SOURCE FILES AND REBUILD.
-- External Dependencies: 1 loaded
-- Namespace File: namespace.lua
-- Entrypoint File: main.lua
-- Core Modules Order: None
-- Scope: global

-- Namespace Content from: namespace.lua
-- Test Mission Namespace
TestMission = {
    name = "Test Mission with Dependencies",
    version = "1.0.0"
}

-- Entrypoint Content from: main.lua
-- Main entry point
function TestMission.start()
    -- Use the test library
    local message = TestLib.greet("DCS World")
    env.info(message)

    local result = TestLib.add(42, 58)
    env.info("The answer is: " .. result)
end

TestMission.start()
