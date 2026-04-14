import { BrowserWindow, Menu, MenuItemConstructorOptions, shell } from "electron";

export function buildMenu(window: BrowserWindow): void {
  const isMac = process.platform === "darwin";

  const template: MenuItemConstructorOptions[] = [
    ...(isMac
      ? ([
          {
            label: "Kinoro",
            submenu: [
              { role: "about" },
              { type: "separator" },
              { role: "services" },
              { type: "separator" },
              { role: "hide" },
              { role: "hideOthers" },
              { role: "unhide" },
              { type: "separator" },
              { role: "quit" },
            ],
          },
        ] as MenuItemConstructorOptions[])
      : []),
    {
      label: "File",
      submenu: [
        {
          label: "New Project…",
          accelerator: "CmdOrCtrl+N",
          click: () => window.webContents.send("menu:newProject"),
        },
        {
          label: "Open Project…",
          accelerator: "CmdOrCtrl+O",
          click: () => window.webContents.send("menu:openProject"),
        },
        { type: "separator" },
        {
          label: "Import from Video Planner…",
          accelerator: "CmdOrCtrl+Shift+I",
          click: () => window.webContents.send("menu:importFromVideoPlanner"),
        },
        { type: "separator" },
        {
          label: "Save",
          accelerator: "CmdOrCtrl+S",
          click: () => window.webContents.send("menu:save"),
        },
        {
          label: "Export…",
          accelerator: "CmdOrCtrl+E",
          click: () => window.webContents.send("menu:export"),
        },
        { type: "separator" },
        isMac ? { role: "close" } : { role: "quit" },
      ],
    },
    {
      label: "Edit",
      submenu: [
        { role: "undo" },
        { role: "redo" },
        { type: "separator" },
        { role: "cut" },
        { role: "copy" },
        { role: "paste" },
        { role: "delete" },
      ],
    },
    {
      label: "View",
      submenu: [
        { role: "reload" },
        { role: "toggleDevTools" },
        { type: "separator" },
        { role: "resetZoom" },
        { role: "zoomIn" },
        { role: "zoomOut" },
        { type: "separator" },
        { role: "togglefullscreen" },
      ],
    },
    {
      role: "help",
      submenu: [
        {
          label: "Project page",
          click: () => shell.openExternal("https://github.com/"),
        },
      ],
    },
  ];

  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}
