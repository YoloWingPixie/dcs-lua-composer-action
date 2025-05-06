require "service"
MyProjectNS.main_executed = true
print("main.lua print check") -- This SHOULD be sanitized
if MyProjectNS.service_loaded then
    print("Service was indeed loaded before main execution!")
end 