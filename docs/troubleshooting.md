[한국어 (Korean)](troubleshooting.ko.md) / [English](troubleshooting.md)

# Troubleshooting

Check the items from top to bottom. The evidence for each item is the Z entries (measurements on a real machine) in `docs/mcu-protocol.md`. No causes beyond those listed here have been confirmed.

## 1. `logic_session wait_ready` returns `no_logic` or times out

1. Is Logic Pro running?
2. Is a project open? With no project open (Logic's "Start" dialog), LCD row 1 shows only ` -` (right after a fresh Logic launch, the whole LCD is blank and there are no strips), and surface commands fail. Open a project (Z11, Z11-b).
3. Is a modal alert showing in the Logic window? While a modal is up, Logic sends nothing to the control surface. Example: unplugging earphones shows "The last selected audio interface is not available", and clicking OK reconnects immediately (Z10).
4. In Logic Pro > Settings > Control Surfaces > Setup… (Logic Pro > 설정 > 컨트롤 서피스 > 설정), is the Mackie Control entry missing or duplicated (2 entries) (Z6, Z14)? Delete only the Mackie Control entry, restart the server (to reconnect the port), let Logic reinstall one entry with default values, then run `logic_session configure`. Do not touch entries for other devices, and do not press "Rebuild Defaults" (기본값 재형성).

## 2. `configure` returns unverified

If a NAME display state is left over (Z12), or PAN row 2 shows `-` (Z17, the surround parameter was `Center` (중앙)), `configure` recovers automatically. If it still fails, go through 1-4 above.

## 3. EQ, PLUGIN, and SEND buttons do not respond

After restarting Logic, these buttons (and PAN and TRACK) may receive no messages (Z6). Use the same procedure as 1-4 above (delete Mackie Control, reconnect, `configure`).

## 4. The plug-in window opens every time you enter the edit view

If the `Open/close plug-in window` (플러그인 윈도우 열기/닫기) checkbox in the CS group of the control surface setup window is on, a plug-in window opens every time you enter the edit view (an item confirmed by capture in Z17). What happens when this checkbox is turned off has not been measured yet.

## 5. `page_to … cursor not responding` (커서 반응 없음)

Right after probing plug-in parameters, the cursor response can be delayed (intermittent, cause unconfirmed, Z16). If there is no response, the server waits 3 more seconds and presses once more. If it still fails, run the same command again.

## 6. After consecutive `set` calls, the value is blank or the previous value

When you move a value with a fader in the edit view, Logic leaves the value overlay up for about 2 seconds (Z15). Read again after 2 seconds. The `set` path has no automatic wait yet.
