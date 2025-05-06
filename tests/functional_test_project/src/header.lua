-- Header for New Functional Test --
MyProjectNS = MyProjectNS or {}
MyProjectNS.header_marker = "Header Was Here"
print("header.lua print check") -- This SHOULD NOT be sanitized if it's a true header file
