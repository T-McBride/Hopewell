# Contact Directory Kiosk

(claude produced)

A self-service touchscreen kiosk for a Raspberry Pi: people enter their own
contact info and take a photo, an admin reviews/approves entries from any
browser on the LAN, and a phone directory (PDF or web page) is generated
from the approved entries.

Built and tested as: FastAPI + SQLite backend, vanilla HTML/JS kiosk and
admin frontends, reportlab for PDF generation. No internet access required
at any point - this is a LAN-only app.

## What's in here

```
app/
  main.py            FastAPI app - all routes
  database.py        SQLite schema + helpers
  auth.py             Admin PIN auth (signed cookie sessions)
  pdf_generator.py     Builds the printable PDF directory as a foldable booklet
  templates/
    directory.html      The always-on browsable web directory
  static/
    kiosk/               Touchscreen self-entry app (index.html, style.css, app.js)
    admin/               Admin console (index.html, style.css, app.js) - PIN protected
  data/                  Created at first run: kiosk.db, photos/, admin_pin.txt
deploy/
  contact-kiosk.service     systemd unit for the backend (HTTP, port 8000)
  contact-kiosk-https.service     systemd unit for the optional HTTPS listener (port 8443)
  kiosk-browser.service     systemd unit that launches Chromium in kiosk mode
  generate_cert.sh          generates the self-signed cert used by the HTTPS listener
certs/                  Created by generate_cert.sh: kiosk.crt, kiosk.key (not checked in)
requirements.txt
```

## 1. Raspberry Pi OS setup

Use Raspberry Pi OS (64-bit), Lite or Desktop. Desktop is simpler for a
first setup since it gives you a windowing environment to run the kiosk
browser in; Lite works if you set up a minimal compositor (e.g. `cage`)
yourself.

Enable the camera (if using the official Pi Camera Module):

```bash
sudo raspi-config
# Interface Options -> Camera -> Enable
sudo reboot
```

For a CSI camera module to show up as a regular webcam that the browser's
`getUserMedia()` can use (this app captures photos in the browser, not via
a native camera library), load the v4l2 compatibility driver:

```bash
echo "bcm2835-v4l2" | sudo tee -a /etc/modules
sudo modprobe bcm2835-v4l2
```

A USB webcam needs no extra setup - it appears as `/dev/video0` automatically.

## 2. Install the app

```bash
sudo apt update
sudo apt install -y python3-venv chromium-browser

git clone <wherever-you-put-this-repo> /home/pi/contact-kiosk
cd /home/pi/contact-kiosk

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Quick manual test before wiring up autostart:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Visit `http://<pi-ip>:8000/kiosk/` from another device on the LAN to try
the self-entry flow, and `http://<pi-ip>:8000/admin-ui/` for the admin
console. **Default admin PIN is `1234` - change it immediately** from the
admin console's Settings panel once you're in.

## 3. Set the backend to autostart

```bash
sudo cp deploy/contact-kiosk.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now contact-kiosk.service
sudo systemctl status contact-kiosk.service
```

Adjust the `User=`, `WorkingDirectory=`, and `ExecStart=` paths in the
service file first if your username or install path differs from
`pi` / `/home/pi/contact-kiosk`.

## 4. Set the kiosk browser to autostart fullscreen

This launches Chromium in kiosk mode pointed at the local app whenever the
Pi boots into its desktop session.

```bash
sudo cp deploy/kiosk-browser.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable kiosk-browser.service
sudo reboot
```

After reboot, the Pi should come up directly into the fullscreen kiosk
screen with no taskbar, no browser chrome, and no way to navigate away.

To get out for maintenance: SSH in from another machine
(`ssh pi@<pi-ip>`) rather than trying to interact with the touchscreen, and
run `sudo systemctl stop kiosk-browser` when you need the screen back.

## 5. Using the admin console day to day

Go to `http://<pi-ip>:8000/admin-ui/` from any laptop/phone on the same
network and log in with the PIN.

- **Pending / Approved / Rejected / All tabs** - filter the contact list
- **Approve / Reject / Edit / Delete** - per-entry actions on each card
- **Settings panel** - toggle whether home addresses are included by
  default when generating a printed directory, generate a one-off PDF with
  or without addresses, view the live web directory, and change the admin
  PIN

The web directory at `/api/directory.html` is always public on the LAN and
never includes home addresses - it's meant to be the everyday "look someone
up" page. Home addresses only ever appear in a PDF that an admin explicitly
generates with that option turned on.

## 6. Enabling the camera from other machines on the LAN

The kiosk touchscreen itself (running its own Chromium pointed at
`http://localhost:8000/kiosk/`) doesn't need anything below - camera
access already works there, since `localhost` is always treated as
secure by the browser, regardless of HTTP/HTTPS.

This section only matters if you want to use the self-entry **camera
capture** from a browser on a *different* machine - e.g. a second
camera station, or just testing `/kiosk/` from your laptop. Browsers
only allow camera/microphone access on a "secure context": `https://`,
or `http://localhost`. A plain `http://192.168.x.x` URL from another
machine doesn't qualify, even on a trusted LAN - the camera will silently
show "unavailable" there. Everything else in the app (forms, admin
console, PDF generation) works fine over the existing plain HTTP setup;
only `getUserMedia()` (the camera call) is affected.

To fix that, run a second copy of the app on a different port with TLS
enabled, just for remote camera access. The existing HTTP setup on port
8000 is untouched - the kiosk and admin console keep working exactly as
before.

**Generate a certificate**, passing the Pi's LAN IP address:

```bash
cd /home/pi/contact-kiosk
./deploy/generate_cert.sh 192.168.1.10
```

This writes `certs/kiosk.crt` and `certs/kiosk.key`, self-signed, valid
for `localhost`, `127.0.0.1`, and the IP you gave it, expiring in 10
years (long-lived on purpose - this is an internal LAN tool, not
something facing the open internet, so there's no need for the
short-lived-cert renewal hassle that's standard for public sites).

**Enable the HTTPS service:**

```bash
sudo cp deploy/contact-kiosk-https.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now contact-kiosk-https.service
sudo systemctl status contact-kiosk-https.service
```

(Adjust the `User=`, `WorkingDirectory=`, and cert paths in that service
file first if your install path or username differs.)

**From another machine**, go to `https://<pi-ip>:8443/kiosk/`. Since the
certificate is self-signed, the browser will show a one-time security
warning the first time - click through it (usually "Advanced" -> "Proceed
anyway", wording varies by browser). That's expected and safe to accept
on a network you control; the warning exists to protect against
impersonation on untrusted networks, which isn't the threat model here.
Most browsers remember that exception afterward, so it's normally a
one-time thing per device.

If you'd rather avoid that warning screen entirely (e.g. for a second
permanent camera station), consider generating the cert with
[mkcert](https://github.com/FiloSottile/mkcert) instead of the included
script, and installing its root CA on that device - mkcert produces
certificates browsers trust automatically with no warning, at the cost
of an extra one-time setup step per device that needs the warning-free
experience.

## The PDF directory is a real foldable booklet

The generated PDF isn't just a flat document - its pages are pre-imposed
for saddle-stitch booklet printing, and it's laid out in three sections,
similar to a classic printed church/community directory:

1. **Cover page** - organization name, contact count, fold/staple instructions
2. **Photo directory** - every approved contact's photo with their name
   underneath, in a grid (2 columns x 4 rows per booklet page)
3. **Alphabetical listing** - a text-only, phone-book style section with
   letter headers (A, B, C...), two columns per page, listing name, phone,
   email, and (if the address toggle is on) home address - no photos here,
   matching a traditional directory's back-section listing
4. A blank **Notes** page at the end

Imposition mechanics:
- Each PDF page is a standard Letter sheet **in landscape**, containing
  two booklet pages side by side at half-letter size
- The page order is rearranged (not 1,2,3... - this is intentional) so
  that printing the sheets in order and folding the whole stack in half
  produces a booklet that reads correctly from front cover to back cover

**To print it correctly:**
1. Print double-sided, with duplex set to **flip on the short edge**
   (landscape content needs short-edge flip, not long-edge - most print
   dialogs have this as an explicit option, sometimes labeled "Short-Edge
   Binding")
2. Stack the printed sheets in order, fold the whole stack in half down
   the middle, and staple along the fold

If your printer doesn't support duplex, print all odd-positioned sheets
first, then flip the stack and feed it back through for the even ones -
most print dialogs have a "print odd pages then even pages" option for
exactly this case.

The total page count is always padded to a multiple of 4 (adding blank
pages at the end if needed) since that's a requirement of this kind of
imposition - a small contact list may come out with a couple of trailing
blank pages, which is normal.

## Updating the frontend after a code change

`style.css` and `app.js` are referenced with a `?v=` query string in both
`kiosk/index.html` and `admin-ui/index.html`. Browsers (especially the
kind of long-lived kiosk browser session this app runs in) will happily
keep serving a stale cached copy of these files indefinitely otherwise.
**Whenever you edit `style.css` or `app.js`, bump that `?v=` number** in
the corresponding `index.html` so browsers are forced to fetch the new
version instead of silently reusing an old one.

## Notes on this being LAN-only

- The app has no outbound internet dependency and doesn't need one
- The main app on port 8000 is plain HTTP - that's a reasonable tradeoff
  for a trusted local network, but don't expose it to the open internet
  or to an untrusted network without adding a reverse proxy with TLS and
  stronger auth first. The optional HTTPS listener on port 8443 (see
  "Enabling the camera from other machines") uses a self-signed cert
  meant only for camera access on this same trusted LAN - it isn't a
  substitute for that kind of hardening either
- The admin PIN is a single shared secret appropriate for a small office,
  not a multi-user permission system

## Extending this

A few things called out during design that aren't built here but would
slot in cleanly:
- A `settings` row already exists for `include_home_address_default`; the
  same table is a natural home for other future global toggles
- The directory generator could be triggered on a schedule (cron calling
  the `/api/admin/directory.pdf` endpoint) rather than only on demand
- A second kiosk on the same LAN can point at this same backend instance
  without any database changes - SQLite is fine for one Pi serving the
  whole office, multiple kiosks all hit the same backend over the network
