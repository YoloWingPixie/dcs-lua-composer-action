-- Enhanced Logger
Logger = {
    levels = {
        DEBUG = 1,
        INFO = 2,
        WARN = 3,
        ERROR = 4
    },
    currentLevel = 2
}

function Logger:log(level, message)
    if level >= self.currentLevel then
        local prefix = ""
        if level == self.levels.DEBUG then prefix = "[DEBUG]"
        elseif level == self.levels.WARN then prefix = "[WARN]"
        elseif level == self.levels.ERROR then prefix = "[ERROR]"
        else prefix = "[INFO]" end

        env.info(prefix .. " " .. message)
    end
end

return Logger
