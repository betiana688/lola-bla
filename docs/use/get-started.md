# Get started

You do this once, with a computer next to the robot. It takes a while the first time, so take it step by step.

## 1. Install

The commands are in the main README, under [Running it](../../README.md#running-it). They download the app, set up its private folders and create an empty database. Nothing is sent anywhere.

## 2. Start Signal's helper, and sign in to the settings

Lola-Bla talks to Signal through a small helper program that runs on the robot and answers only to the robot itself. The README shows how to start it, how to create your settings login and the certificate, and how to start the settings page.

Then open the settings page in your browser: `https://reachy-mini.local:9443/` (or `https://` and the robot's IP address, with `:9443` at the end).

- Your browser will warn that the certificate is not trusted. That is expected: the robot made the certificate itself, so no outside company vouches for it. Continue once; the page is protected by your password.
- If the name does not work, use the robot's IP address. Reachy Mini Control or your router shows it.

## 3. Link Signal

On the **Signal** page, press link and scan the QR code with your phone (Signal, Settings, Linked devices). The robot then appears as a device called `reachy-mini`. Your phone number is never shown in full.

## 4. Choose who can talk to Lola

Nobody can reach her until you say so.

- **Groups:** add the family Signal groups you want her to check, and give each a short **spoken name** (for example "Papa and Mama"). Lola picks a group by that name, so two groups cannot sound the same.
- **Contacts:** inside each group, add the people whose messages count. Only people who are in your Signal contacts **with a phone number** can be approved, so you know the number of everyone who can talk to her. Being in an approved group is not enough.
- Removing a group or a contact asks for your password and deletes their messages and recordings on the robot.

## 5. Start the app

Start **lola_bla** from the Applications tab in Reachy Mini Control, or from the command line (see the README). Two settings you will probably want:

- **Start when the robot wakes up.** On the settings home page, the last card has a switch for this. With it on, touching an antenna on the sleeping robot wakes it and starts Lola-Bla a few seconds later. It asks for your password, because it changes how the robot behaves.
- **Settings from Control.** The Lola-Bla panel in Control shows a small page with its status. The settings themselves open in your browser, never inside Control: see [daily use](daily-use.md#the-settings-page).

You are ready. Say hello to Lola.

Next: [daily use](daily-use.md).
