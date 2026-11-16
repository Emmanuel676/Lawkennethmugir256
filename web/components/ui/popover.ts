// The shared look of floating panels (menus, selects, dialogs, tooltips): brand surface, line and soft shadow.
export const popover =
  "z-50 rounded-xl border border-line bg-surface text-ink shadow-[0_10px_30px_-10px_rgba(15,23,42,0.35),0_2px_6px_rgba(15,23,42,0.06)] " +
  "data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 " +
  "data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95";
