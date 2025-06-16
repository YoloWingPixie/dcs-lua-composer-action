-- Utility Library
Utils = {}

function Utils.formatTime(seconds)
    local hours = math.floor(seconds / 3600)
    local mins = math.floor((seconds % 3600) / 60)
    local secs = seconds % 60
    return string.format("%02d:%02d:%02d", hours, mins, secs)
end

function Utils.randomPoint(center, radius)
    local angle = math.random() * 2 * math.pi
    local r = math.sqrt(math.random()) * radius
    return {
        x = center.x + r * math.cos(angle),
        z = center.z + r * math.sin(angle)
    }
end

return Utils
