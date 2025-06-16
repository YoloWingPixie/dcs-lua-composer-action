-- Mission using multiple dependencies
function ComplexMission.run()
    -- Use Logger
    Logger:log(Logger.levels.INFO, "Mission starting...")

    -- Use Utils
    local missionTime = 3661  -- 1 hour, 1 minute, 1 second
    local timeStr = Utils.formatTime(missionTime)
    Logger:log(Logger.levels.INFO, "Mission time: " .. timeStr)

    -- Generate random point
    local base = {x = 1000, z = 2000}
    local randomPos = Utils.randomPoint(base, 500)
    Logger:log(Logger.levels.DEBUG, string.format("Random position: x=%.2f, z=%.2f", randomPos.x, randomPos.z))

    -- Another random point
    local enemyBase = {x = 5000, z = 8000}
    local enemyPos = Utils.randomPoint(enemyBase, 1000)
    Logger:log(Logger.levels.INFO, string.format("Enemy spotted at: x=%.2f, z=%.2f", enemyPos.x, enemyPos.z))

    -- Calculate mission progress
    local progress = 75.5
    Logger:log(Logger.levels.WARN, "Mission " .. progress .. "% complete")

    Logger:log(Logger.levels.INFO, "Mission initialized successfully!")
end

ComplexMission.run()
