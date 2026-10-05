-- Forward declaration: B is an upvalue in A, assigned later. Correct.
local B

local function A()
  return B()
end

B = function()
  return 1
end

return A
