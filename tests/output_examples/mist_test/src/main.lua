-- Main mission script using MIST
function AdvancedMission.init()
    env.info("Initializing Advanced Mission with MIST")

    -- Check if MIST is loaded
    if mist then
        env.info("MIST version: " .. (mist.majorVersion or "unknown"))

        -- Example: Schedule a function using MIST
        mist.scheduleFunction(function()
            env.info("This message is scheduled by MIST!")
        end, {}, timer.getTime() + 10)

        -- Example: Use MIST utilities
        local vec3 = {x = 100, y = 0, z = 200}
        local distance = mist.utils.get2DDist({x = 0, z = 0}, vec3)
        env.info("Distance from origin: " .. distance)
    else
        env.warning("MIST not loaded!")
    end
end

AdvancedMission.init()
