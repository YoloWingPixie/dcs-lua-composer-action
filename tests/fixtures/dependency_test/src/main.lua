-- Main entry point
function TestMission.start()
    -- Use the test library
    local message = TestLib.greet("DCS World")
    env.info(message)

    local result = TestLib.add(42, 58)
    env.info("The answer is: " .. result)
end

TestMission.start()
