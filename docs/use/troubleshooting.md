# When something is off

## The settings do not open from Reachy Mini Control

That is normal inside the panel. Use the **arrow icon**, then **open settings**, or **copy** the address into your browser. See [daily use](daily-use.md#the-settings-page). The browser warns about the certificate once: continue, the robot made it itself.

## `reachy-mini.local` does not work, but the IP address does

Some computers turn the name into an address the settings page does not listen on. Use `https://<robot IP>:9443/`. If the robot gets a new IP address from your router, the page in Control follows it by itself; restart Lola-Bla once so the settings page learns it too.

## Reachy Mini Control stops the app after a minute

Control stops an app when it cannot reach the app's web page. Lola-Bla serves a small page for exactly this reason, so start it as the app `lola_bla` and do not remove that page.

## The panel says "not linked yet" for Signal

Open the settings, go to **Signal**, and link again. If you removed the robot under Linked devices on your phone, the settings show "Removed from Signal" and offer a clean-up.

## The Signal page says "Cannot tell"

Signal's helper answers one thing at a time, so it can be busy for up to a minute. Wait and reload.

## Lola ignores a message

Messages from people who are not approved are ignored on purpose. A person who hides their phone number from group members may also arrive without a number, and Lola cannot tell who it is. The activity log shows it.

## Lola does not wake, or does not start

The robot always starts asleep. Touch an antenna gently. If nothing happens, check that "start when the robot wakes up" is on in the settings, or start `lola_bla` in Control. Another app can hold the slot: only one app runs at a time.

## The left antenna shows an overload error

I have seen this a few times with the robot's own motor reboot afterwards, and do not know the cause yet. Touch the antennas gently.

## I forgot the settings password

On the robot: `python3 console/manage.py reset-password` (from the repo folder, inside its Python environment). It also clears a lockout.

Still stuck? Open an issue in the repository and say what you saw. Please do not paste phone numbers, tokens or logs without checking them first.
