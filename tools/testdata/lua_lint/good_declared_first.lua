-- Helper is declared before anything references it. Correct.
local function Helper()
  return 1
end

local function Outer()
  return Helper()
end

return Outer()
