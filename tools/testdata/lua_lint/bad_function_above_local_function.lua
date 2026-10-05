-- Outer is compiled before `local function Helper` exists, so its call
-- to Helper binds the GLOBAL Helper (nil at runtime).
local function Outer()
  return Helper()
end

local function Helper()
  return 1
end

return Outer, Helper
