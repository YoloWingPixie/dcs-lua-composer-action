-- Mock MIST (Mission Scripting Tools)
-- This is a simplified mock for demonstration purposes
-- Real MIST is much more comprehensive

mist = {}
mist.majorVersion = 4
mist.minorVersion = 5
mist.build = 126

-- Core MIST tables
mist.flagFuncs = {}
mist.mapObjs = {}
mist.DBs = {}
mist.dynAdd = {}
mist.utils = {}
mist.vec = {}
mist.goRoute = {}
mist.ground = {}

-- Some basic MIST utilities
mist.utils.get2DDist = function(point1, point2)
    local xDiff = point1.x - point2.x
    local zDiff = point1.z - point2.z
    return math.sqrt(xDiff * xDiff + zDiff * zDiff)
end

mist.utils.get3DDist = function(point1, point2)
    local xDiff = point1.x - point2.x
    local yDiff = (point1.y or 0) - (point2.y or 0)
    local zDiff = point1.z - point2.z
    return math.sqrt(xDiff * xDiff + yDiff * yDiff + zDiff * zDiff)
end

mist.utils.makeVec3 = function(vec2, y)
    if not vec2.z then
        return {x = vec2.x, y = y or 0, z = vec2.y}
    else
        return {x = vec2.x, y = y or vec2.y or 0, z = vec2.z}
    end
end

-- Scheduler function
mist.scheduleFunction = function(fn, vars, time)
    timer.scheduleFunction(fn, vars, time)
end

-- Message functions
mist.message = {}
mist.message.add = function(msgTable)
    trigger.action.outText(msgTable.text or "", msgTable.displayTime or 10)
end

env.info("MIST " .. mist.majorVersion .. "." .. mist.minorVersion .. "." .. mist.build .. " loaded")

return mist
