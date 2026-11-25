-- Forever STUwave: Config page, Data bar
-- A page shell: one tab for the segment rows, with the preview band slot (CW.PageBody("data") and UI.Band) the data bar
-- ticket (E1) fills.

local _, FS = ...

local CW = FS.ConfigWindow

CW.RegisterCategory({
    key = "data", label = "Data bar", group = "PANELS", order = 5,
    tabs = { { key = "g", label = "Segments", build = function() end } },
})
