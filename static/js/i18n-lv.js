/* static/js/i18n-lv.js — Latvian for the client dashboard (an optional extra; English is always the default).
   Swaps the dashboard's own wording on the page; the client's own content (reviews, service text, names)
   is left as written. Anything not listed here simply stays in English.
   Switch: the EN | LV pill at the top right (saved per device in localStorage "lang"). */
(function () {
  var lang = null;
  try { lang = localStorage.getItem("lang"); } catch (e) {}
  var root = document.documentElement;
  function done() { root.classList.remove("lv-pending"); }
  if (lang !== "lv") { done(); return; }

  var D = {
    /* shell + nav */
    "Skip to content": "Pāriet uz saturu", "Dashboard": "Vadības panelis", "Home": "Sākums", "My website": "Mana vietne",
    "Visitors": "Apmeklētāji", "Reviews": "Atsauksmes", "Posts": "Ieraksti", "Jobs": "Darbi", "Calendar": "Kalendārs",
    "My plan": "Mans plāns", "Settings": "Iestatījumi", "Help": "Palīdzība", "Website": "Vietne", "Log out": "Iziet",
    "Ask": "Lūgt", "Quick": "Ātrās saites", "Open menu": "Atvērt izvēlni", "Switch theme": "Mainīt motīvu",
    "Switch to light theme": "Pārslēgt uz gaišo motīvu", "Back to admin": "Atpakaļ uz administrāciju",
    "Add this app to your home screen": "Pievienojiet šo lietotni sākuma ekrānam",
    "Open your dashboard in one tap.": "Atveriet savu paneli ar vienu pieskārienu.", "Tap": "Pieskarieties",
    "then": "tad", "Add to Home Screen": "Pievienot sākuma ekrānam", "Add to Home screen": "Pievienot sākuma ekrānam",
    "Browser menu (⋮) →": "Pārlūka izvēlne (⋮) →", "Install": "Instalēt", "Not now": "Ne tagad", "the Share button": "kopīgošanas poga",
    /* report an issue */
    "⚑ Report an issue with this page": "⚑ Ziņot par problēmu šajā lapā", "Report an issue": "Ziņot par problēmu",
    "Something not working, confusing, or looks wrong? Tell Aaron and he'll sort it.": "Kaut kas nedarbojas, ir neskaidrs vai izskatās nepareizi? Pastāstiet Āronam, un viņš to sakārtos.",
    "What went wrong?": "Kas notika?", "It happened on the page before this one": "Tas notika iepriekšējā lapā",
    "We'll include which page you're on and your type of phone or computer, to help find the problem.": "Mēs pievienosim, kurā lapā esat un kāds ir jūsu tālrunis vai dators, lai vieglāk atrastu problēmu.",
    "Send to Aaron": "Nosūtīt Āronam", "Cancel": "Atcelt", "e.g. I pressed Save and nothing happened": "piem., nospiedu Saglabāt, bet nekas nenotika",
    "Sending…": "Sūta…", "Thanks! Aaron has been told and will look into it.": "Paldies! Ārons ir informēts un to apskatīs.",
    /* home */
    "Ask for a review": "Lūgt atsauksmi", "Post an update": "Publicēt jaunumu", "Edit my website": "Rediģēt manu vietni",
    "Visitors (30 days)": "Apmeklētāji (30 dienas)", "Waiting for a reply": "Gaida atbildi", "reviews to thank": "atsauksmes, par kurām pateikties",
    "Tip": "Padoms", "Next tip": "Nākamais padoms", "none yet": "vēl nav", "No new reviews yet this month.": "Šomēnes vēl nav jaunu atsauksmju.",
    "Reply to your reviews, even with a quick thank-you. New customers read the replies too.": "Atbildiet uz atsauksmēm, kaut vai ar īsu paldies. Jaunie klienti lasa arī atbildes.",
    "Posting photos of finished jobs keeps your website fresh, and Google tends to show fresh websites higher.": "Pabeigto darbu foto uztur jūsu vietni svaigu, un Google svaigas vietnes parasti rāda augstāk.",
    "Mention the town in your posts, like “New bathroom in Tettenhall”. It helps local people find you on Google.": "Ierakstos minējiet pilsētu, piem., “Jauna vannasistaba Tettenhallā”. Tas palīdz vietējiem jūs atrast Google.",
    "Every new review helps. Ask at the end of each job, while the customer is happy with the work.": "Katra jauna atsauksme palīdz. Lūdziet to katra darba beigās, kamēr klients ir apmierināts.",
    "Reviews on Google count most for “near me” searches. After someone reviews you here, we offer them a one-tap way to post it on Google too.": "Google atsauksmes ir vissvarīgākās meklējumiem “tuvumā”. Kad kāds šeit atstāj atsauksmi, mēs piedāvājam to ar vienu pieskārienu publicēt arī Google.",
    "Share your posts on Facebook and Instagram. Every share sends people back to your website.": "Dalieties ar ierakstiem Facebook un Instagram. Katra dalīšanās atved cilvēkus uz jūsu vietni.",
    "Keep your photos up to date. You can put your best (or most-liked) photos at the top of your homepage.": "Uzturiet foto aktuālus. Labākos (vai visvairāk iecienītos) varat likt sākumlapas augšā.",
    "Going on holiday? Turn on Away mode in Settings so customers know when you're back.": "Dodaties atvaļinājumā? Iestatījumos ieslēdziet prombūtnes režīmu, lai klienti zinātu, kad atgriezīsieties.",
    "Send quotes from your dashboard. Customers can accept with one tap, and it goes straight into your calendar.": "Sūtiet tāmes no sava paneļa. Klienti tās var apstiprināt ar vienu pieskārienu, un darbs uzreiz nonāk kalendārā.",
    /* my website */
    "Tap anything to change it. Changes show on your site within 10 minutes.": "Pieskarieties jebkam, lai to mainītu. Izmaiņas vietnē parādās 10 minūšu laikā.",
    "View my website ↗": "Skatīt manu vietni ↗", "Top-of-page photo": "Galvenais foto", "Top-of-page photos": "Galvenie foto",
    "Random from all": "Nejauši no visiem", "Most-liked": "Visvairāk iecienītie", "Your picks": "Jūsu izvēlētie",
    "Photos": "Foto", "Services": "Pakalpojumi", "Something bigger?": "Kaut kas lielāks?", "Ask Aaron": "Jautāt Āronam",
    "Find something to change": "Atrast, ko mainīt", "🔎  Find something to change…": "🔎  Atrast, ko mainīt…",
    "Add or remove": "Pievienot vai noņemt", "Gallery photos": "Galerijas foto", "Your photos": "Jūsu foto",
    "Original wording": "Sākotnējais teksts", "Edit": "Rediģēt", "Heading": "Virsraksts", "Intro": "Ievads", "Name": "Nosaukums",
    "Description": "Apraksts", "Save": "Saglabāt", "Undo or go back to the original": "Atsaukt vai atjaunot sākotnējo",
    "Nothing matches. Try another word, or": "Nekas neatbilst. Mēģiniet citu vārdu vai", "ask Aaron": "jautājiet Āronam",
    "Sections": "Sadaļas", "Edited": "Rediģēts", "Undo last change": "Atsaukt pēdējo izmaiņu", "Back to original": "Atpakaļ uz sākotnējo",
    "Saved. Your website updates within 10 minutes.": "Saglabāts. Jūsu vietne atjaunosies 10 minūšu laikā.", "No changes to save.": "Nav izmaiņu, ko saglabāt.",
    "Add photos": "Pievienot foto", "from your phone or computer": "no tālruņa vai datora",
    /* top-of-page photo */
    "The big photo people see first on your homepage. A different one is picked each visit.": "Lielais foto, ko cilvēki redz pirmo jūsu sākumlapā. Katrā apmeklējumā tiek izvēlēts cits.",
    "Visitors can tap ♥ on photos in your gallery. Choose": "Apmeklētāji var nospiest ♥ uz foto jūsu galerijā. Izvēlieties",
    "most-liked": "visvairāk iecienītos", "to show the favourites at the top of your homepage, or tick your own.": "lai sākumlapas augšā rādītu iecienītākos, vai atzīmējiet savus.",
    "Random from all my photos": "Nejauši no visiem maniem foto", "Random from my most-liked photos": "Nejauši no maniem iecienītākajiem foto",
    "Random from photos I choose": "Nejauši no foto, ko izvēlos es", "Most liked first · tick for \"photos I choose\"": "Iecienītākie vispirms · atzīmējiet “foto, ko izvēlos es”",
    "How does this work?": "Kā tas darbojas?",
    /* visitors */
    "How many people visit your website, and how they find you.": "Cik cilvēku apmeklē jūsu vietni un kā viņi jūs atrod.",
    "How do I get more visitors?": "Kā iegūt vairāk apmeklētāju?", "Visits, last 30 days": "Apmeklējumi, pēdējās 30 dienas",
    "From Google": "No Google", "people who searched and found you": "cilvēki, kas meklēja un atrada jūs", "Busiest day": "Aktīvākā diena",
    "visits in one day": "apmeklējumi vienā dienā", "Visits per day": "Apmeklējumi dienā", "last 30 days": "pēdējās 30 dienas",
    "Today": "Šodien", "Where visitors came from": "No kurienes nāca apmeklētāji", "Typed in / bookmarks / apps": "Ievadīts / grāmatzīmes / lietotnes",
    "Most visited pages": "Apmeklētākās lapas", "Homepage": "Sākumlapa", "Privacy": "Privātums", "Terms": "Noteikumi",
    "No visits counted yet.": "Apmeklējumi vēl nav saskaitīti.", "Counting started recently": "Skaitīšana sākta nesen",
    "Counted without cookies or tracking: just the page and the site people came from. Search engines and bots aren't counted.": "Skaitīts bez sīkdatnēm un izsekošanas: tikai lapa un vietne, no kuras cilvēki atnāca. Meklētājprogrammas un roboti netiek skaitīti.",
    "Post photos of finished jobs (mention the town), ask every happy customer for a review, and reply to reviews. Google notices sites that are kept fresh and that customers talk about.": "Publicējiet pabeigto darbu foto (miniet pilsētu), lūdziet atsauksmi katram apmierinātam klientam un atbildiet uz atsauksmēm. Google pamana vietnes, kas tiek atjaunotas un par kurām klienti runā.",
    /* reviews */
    "Your reviews": "Jūsu atsauksmes", "Everything here shows on your website. Replying shows customers you care.": "Viss šeit tiek rādīts jūsu vietnē. Atbildot jūs parādāt, ka klienti jums rūp.",
    "Add a review": "Pievienot atsauksmi", "All": "Visas", "Needs a reply": "Jāatbild", "via Google ↗": "no Google ↗", "Reply": "Atbildēt",
    "Save reply": "Saglabāt atbildi", "Remove reply": "Noņemt atbildi", "Report this review": "Ziņot par šo atsauksmi",
    "For fake, abusive or wrong-business reviews only. HapiTech checks every report. By law, genuine reviews (good or bad) have to stay up.": "Tikai viltotām, aizskarošām vai citam uzņēmumam domātām atsauksmēm. HapiTech pārbauda katru ziņojumu. Saskaņā ar likumu īstām atsauksmēm (labām vai sliktām) jāpaliek redzamām.",
    "Send report": "Nosūtīt ziņojumu", "5 out of 5 stars": "5 no 5 zvaigznēm", "Why should we check it?": "Kāpēc mums tā jāpārbauda?",
    "Verified customer": "Pārbaudīts klients", "Approve": "Apstiprināt", "It's spam": "Tas ir surogātpasts",
    "Approved. It shows on your website within 10 minutes.": "Apstiprināts. Tā parādīsies jūsu vietnē 10 minūšu laikā.",
    "Got a review on Google, Facebook or Checkatrade? Copy it in here, word for word, so it shows on your website too.": "Saņēmāt atsauksmi Google, Facebook vai Checkatrade? Ielīmējiet to šeit vārds vārdā, lai tā parādītos arī jūsu vietnē.",
    "Where is it from?": "No kurienes tā ir?", "Added manually": "Pievienota manuāli", "Stars": "Zvaigznes", "Coming soon": "Drīzumā",
    "Google reviews coming in by themselves. We're waiting on access from Google.": "Google atsauksmes nāks pašas. Gaidām piekļuvi no Google.",
    "Their name, as shown on the review": "Vārds, kā norādīts atsauksmē", "What they wrote": "Ko viņi uzrakstīja", "Date": "Datums",
    "optional": "nav obligāti", "Add review": "Pievienot atsauksmi",
    "Waiting on Google API access. Once it's approved, your Google reviews will come in by themselves and you'll be able to reply to them from here. For now, copy them in by hand.": "Gaidām Google API piekļuvi. Kad tā būs apstiprināta, jūsu Google atsauksmes nāks pašas un uz tām varēsiet atbildēt no šejienes. Pagaidām tās ielīmējiet manuāli.",
    "Review added. It shows on your website within 10 minutes.": "Atsauksme pievienota. Tā parādīsies jūsu vietnē 10 minūšu laikā.",
    /* posts */
    "Show off finished jobs. Posts with the town name help local people find you.": "Parādiet pabeigtos darbus. Ieraksti ar pilsētas nosaukumu palīdz vietējiem jūs atrast.",
    "New post": "Jauns ieraksts", "Published": "Publicēts", "Draft": "Melnraksts", "Title": "Virsraksts", "Town": "Pilsēta",
    "optional, helps local searches": "nav obligāti, palīdz vietējā meklēšanā", "A few words": "Daži vārdi", "up to 6 per post": "līdz 6 vienā ierakstā",
    "Also add the photos to my website gallery": "Pievienot foto arī manas vietnes galerijai", "Publish": "Publicēt", "Save draft": "Saglabāt melnrakstu",
    "Unpublish": "Atcelt publicēšanu", "Delete": "Dzēst", "Edit post": "Rediģēt ierakstu",
    "What you did, how long it took, anything the customer loved.": "Ko izdarījāt, cik ilgi tas aizņēma, kas klientam patika.",
    "Share it": "Dalīties", "Share with photos": "Dalīties ar foto", "Copy text": "Kopēt tekstu", "Copied ✓": "Nokopēts ✓",
    "Every share sends people to your website. On your phone, “Share with photos” lets you pick Facebook, Instagram, WhatsApp and more.": "Katra dalīšanās atved cilvēkus uz jūsu vietni. Tālrunī “Dalīties ar foto” ļauj izvēlēties Facebook, Instagram, WhatsApp un citus.",
    "Instagram: tap “Share with photos” on your phone and choose Instagram (it needs a photo).": "Instagram: tālrunī pieskarieties “Dalīties ar foto” un izvēlieties Instagram (vajadzīgs foto).",
    "Saved as a draft.": "Saglabāts kā melnraksts.", "Post deleted.": "Ieraksts izdzēsts.",
    /* jobs */
    "Every enquiry, from first contact to paid.": "Katrs pieprasījums, no pirmā kontakta līdz apmaksai.", "Add a job": "Pievienot darbu",
    "Quote requests from your website land here automatically. Add phone enquiries with": "Tāmju pieprasījumi no jūsu vietnes nonāk šeit automātiski. Tālruņa pieprasījumus pievienojiet ar",
    "Open a job to send a": "Atveriet darbu, lai nosūtītu", "quote": "tāmi", ". When they accept, pick a": ". Kad klients piekrīt, izvēlieties",
    "date": "datumu", "and it goes in your calendar.": "un tas nonāk kalendārā.", "After the work, tap": "Pēc darba pieskarieties",
    "Done": "Pabeigts", ": we can email them a review link. Then send the": ": mēs varam nosūtīt saiti atsauksmei. Tad nosūtiet",
    "invoice": "rēķinu", "Jobs that don't go ahead are deleted after 30 days. Finished jobs are kept:": "Darbi, kas nenotiek, tiek dzēsti pēc 30 dienām. Pabeigtie darbi tiek saglabāti:",
    "archive": "arhivējiet", "them to tidy up.": "tos, lai sakārtotu.", "Open": "Aktīvie", "New": "Jauns", "Quoted": "Tāme nosūtīta",
    "Booked": "Ieplānots", "Archive": "Arhīvs", "Accepted": "Apstiprināts", "Nothing here": "Šeit nekā nav",
    "Archived jobs are kept here until you delete them.": "Arhivētie darbi tiek glabāti šeit, līdz tos izdzēšat.",
    "Customer's name": "Klienta vārds", "Email": "E-pasts", "for quotes, reminders and invoices": "tāmēm, atgādinājumiem un rēķiniem",
    "Phone": "Tālrunis", "Postcode": "Pasta indekss", "How did they get in touch?": "Kā viņi sazinājās?", "Phone / text": "Tālrunis / īsziņa",
    "Other": "Cits", "The job": "Darbs", "Details": "Sīkāka informācija", "Address": "Adrese", "optional, only if you need it": "nav obligāti, tikai ja vajag",
    "Add job": "Pievienot darbu", "e.g. Fit two wardrobes": "piem., uzstādīt divus skapjus", "Next step": "Nākamais solis",
    "Send another quote": "Nosūtīt vēl vienu tāmi", "Write a quote": "Sagatavot tāmi", "or, if it's already agreed:": "vai, ja jau ir norunāts:",
    "Start time": "Sākuma laiks", "How many days?": "Cik dienas?", "Book it in": "Ieplānot", "Quotes & invoices": "Tāmes un rēķini",
    "Sent": "Nosūtīts", "Customer": "Klients", "Private notes": "Privātas piezīmes", "Not going ahead": "Nenotiks",
    "Mark as not going ahead? It'll be deleted in 30 days.": "Atzīmēt, ka darbs nenotiks? Tas tiks dzēsts pēc 30 dienām.",
    "Delete this job and the customer's details for good?": "Neatgriezeniski dzēst šo darbu un klienta datus?",
    "Delete this as spam?": "Dzēst kā surogātpastu?", "Deleted as spam.": "Izdzēsts kā surogātpasts.", "What they asked": "Ko viņi jautāja",
    "From your website": "No jūsu vietnes", "Booking request": "Rezervācijas pieprasījums", "Added by you": "Pievienojāt jūs",
    "Job done ✓": "Darbs pabeigts ✓", "Email them a review link": "Nosūtīt saiti atsauksmei", "Change the date": "Mainīt datumu",
    "Save new date": "Saglabāt jauno datumu", "Send the invoice": "Nosūtīt rēķinu", "Remind them next time": "Atgādināt nākamreiz",
    "Set reminder": "Iestatīt atgādinājumu", "Reopen": "Atvērt atkārtoti", "Move back to jobs": "Atgriezt darbos",
    "Accepted jobs are kept. Archive it first if you want to delete it.": "Apstiprinātie darbi tiek saglabāti. Lai dzēstu, vispirms arhivējiet.",
    /* quotes */
    "Quote": "Tāme", "Invoice": "Rēķins", "Add a line for each part of the job, e.g. \"Labour, 1 day\" or \"Materials\".": "Pievienojiet rindu katrai darba daļai, piem., “Darbs, 1 diena” vai “Materiāli”.",
    "Send": "Nosūtīt", "What": "Kas", "Qty": "Daudz.", "£ each": "£ par vienību", "+ Add a line": "+ Pievienot rindu", "VAT %": "PVN %",
    "Valid until": "Derīga līdz", "Notes for the customer": "Piezīmes klientam", "Save and email it": "Saglabāt un nosūtīt",
    "Labour": "Darbs", "so they show on the quote.": "lai tie būtu redzami tāmē.", "Add your address in": "Pievienojiet savu adresi sadaļā",
    "emails Demo a link to view it and accept it. They can print it or save it as a PDF from there.": "nosūta saiti, lai to apskatītu un apstiprinātu. No turienes to var izdrukāt vai saglabāt kā PDF.",
    /* calendar */
    "Your booked jobs. They can show in your phone's calendar too.": "Jūsu ieplānotie darbi. Tie var parādīties arī tālruņa kalendārā.",
    "Nothing booked yet": "Vēl nekas nav ieplānots", "When you book a job in, it shows here.": "Kad ieplānosiet darbu, tas parādīsies šeit.",
    "Add to your phone's calendar": "Pievienot tālruņa kalendāram", "How?": "Kā?", "Copy link": "Kopēt saiti",
    "Make a new link (if this one was shared by mistake)": "Izveidot jaunu saiti (ja šī tika kopīgota kļūdas pēc)",
    "Make a new link? The old one stops working.": "Izveidot jaunu saiti? Vecā vairs nedarbosies.",
    "New bookings show up within an hour or so. Keep this link private: it shows your customers' names and postcodes.": "Jaunas rezervācijas parādās aptuveni stundas laikā. Glabājiet šo saiti privāti: tajā redzami klientu vārdi un pasta indeksi.",
    /* my plan */
    "Your plan, the work done on your website, and what's included.": "Jūsu plāns, paveiktais darbs pie vietnes un kas ir iekļauts.",
    "Your plan": "Jūsu plāns", "Full plan": "Pilnais plāns", "Friends plan": "Draugu plāns", "Free trial": "Bezmaksas izmēģinājums",
    "Everything in your dashboard is included.": "Viss jūsu panelī ir iekļauts.",
    "Everything in your dashboard is included, on top of us looking after your website.": "Viss jūsu panelī ir iekļauts, papildus tam, ka rūpējamies par jūsu vietni.",
    "Anything to pay?": "Vai kaut kas jāmaksā?", "Nothing to pay. You're all square ✓": "Nekas nav jāmaksā. Viss nokārtots ✓",
    "Aaron will be in touch about how to pay.": "Ārons sazināsies par apmaksu.", "Your orders": "Jūsu pasūtījumi",
    "Website build & launch": "Vietnes izveide un palaišana", "Website creation": "Vietnes izveide", "Server setup": "Servera iestatīšana",
    "Deployment": "Publicēšana", "Email setup": "E-pasta iestatīšana", "Domain registration": "Domēna reģistrācija",
    "Server hosting": "Servera mitināšana", "Domain renewal": "Domēna atjaunošana", "💛 Covered by your plan": "💛 Sedz jūsu plāns",
    "Total": "Kopā", "Covered by your plan": "Sedz jūsu plāns", "You paid": "Jūs samaksājāt", "Saved on this plan": "Ietaupīts ar šo plānu",
    "Questions about anything here?": "Jautājumi par kaut ko šeit?", "Message Aaron": "Rakstiet Āronam",
    "☕ Fancy saying thanks?": "☕ Vēlaties pateikt paldies?", "Support HapiTech": "Atbalstīt HapiTech",
    "Totally optional, and your plan stays exactly the same either way. If you'd like to chip in towards the running costs, it's very much appreciated.": "Pilnīgi brīvprātīgi, un jūsu plāns jebkurā gadījumā paliek tāds pats. Ja vēlaties piedalīties uzturēšanas izmaksās, mēs to ļoti novērtēsim.",
    /* settings */
    "🎨 Dashboard look": "🎨 Paneļa izskats", "just on this device": "tikai šajā ierīcē", "Colours": "Krāsas", "Your brand colours": "Jūsu zīmola krāsas",
    "HapiTech blue": "HapiTech zilā", "Theme": "Motīvs", "🌙 Dark": "🌙 Tumšs", "☀️ Light": "☀️ Gaišs", "🏖️ Away mode": "🏖️ Prombūtnes režīms",
    "Going on holiday? Your website shows a short notice and booking requests are paused until you're back.": "Dodaties atvaļinājumā? Jūsu vietnē būs īss paziņojums, un rezervācijas tiks apturētas, līdz atgriezīsieties.",
    "Back on": "Atpakaļ", "Message": "Ziņa", "I'm back": "Esmu atpakaļ", "Logins": "Pieteikšanās", "+ Add a helper": "+ Pievienot palīgu",
    "What can helpers do?": "Ko var palīgi?", "Add helper": "Pievienot palīgu", "On your quotes & invoices": "Jūsu tāmēs un rēķinos",
    "Email customers reply to": "E-pasts, uz kuru klienti atbild", "VAT number": "PVN numurs", "leave blank if you're not VAT registered": "atstājiet tukšu, ja neesat PVN maksātājs",
    "Business address": "Uzņēmuma adrese", "How customers pay you": "Kā klienti jums maksā", "shown on invoices, e.g. bank, sort code, account number": "redzams rēķinos, piem., banka, kods, konta numurs",
    "optional, shown on quotes": "nav obligāti, redzams tāmēs", "Away until 3 January. Quote requests are still welcome!": "Prom līdz 3. janvārim. Tāmju pieprasījumi joprojām laipni gaidīti!",
    "Quote valid for 30 days. Materials charged at cost.": "Tāme derīga 30 dienas. Materiāli par pašizmaksu.",
    "Helpers (a partner or apprentice) can see jobs and the calendar, mark jobs done, ask for reviews and post updates. They can't see quotes, invoices or settings, or change the website.": "Palīgi (partneris vai māceklis) var redzēt darbus un kalendāru, atzīmēt darbus kā pabeigtus, lūgt atsauksmes un publicēt jaunumus. Viņi neredz tāmes, rēķinus un iestatījumus un nevar mainīt jūsu vietni.",
    /* help */
    "Quick guides. Can't find it? Ask below and Aaron will help.": "Īsas pamācības. Nevarat atrast? Jautājiet zemāk, un Ārons palīdzēs.",
    "⭐ Get a review after a job": "⭐ Saņemt atsauksmi pēc darba", "💼 From enquiry to invoice": "💼 No pieprasījuma līdz rēķinam",
    "📅 See jobs in your phone's calendar": "📅 Redzēt darbus tālruņa kalendārā", "📱 Put this app on your home screen": "📱 Pievienot lietotni sākuma ekrānam",
    "📸 Post your work": "📸 Publicēt savus darbus", "✏️ Change your website": "✏️ Mainīt savu vietni", "🏖️ Going on holiday": "🏖️ Dodaties atvaļinājumā",
    "👷 Give a helper a login": "👷 Piešķirt palīgam pieeju", "🔑 Logging in": "🔑 Pieteikšanās",
    "There's no password. Enter your email and we send you a 6-digit code. Tick \"Keep me logged in\" on your own phone.": "Paroles nav. Ievadiet e-pastu, un mēs nosūtīsim 6 ciparu kodu. Savā tālrunī atzīmējiet “Palikt pieteiktam”.",
    "A question, or a change you'd like": "Jautājums vai vēlamās izmaiņas", "Or email": "Vai rakstiet uz", "e.g. Can we add a page for kitchen fitting?": "piem., vai varam pievienot lapu par virtuves uzstādīšanu?",
    "Reviews appear on your website within 10 minutes.": "Atsauksmes jūsu vietnē parādās 10 minūšu laikā.",
    "Not with them? Type their email instead and we'll send the link.": "Neesat kopā? Ierakstiet viņu e-pastu, un mēs nosūtīsim saiti.",
    "Sent to HapiTech. Aaron will be in touch.": "Nosūtīts HapiTech. Ārons sazināsies.",
    /* ask */
    "Job done? 🎉": "Darbs pabeigts? 🎉", "Ask while you're still there. Most people say yes on the spot.": "Lūdziet, kamēr vēl esat tur. Lielākā daļa piekrīt uzreiz.",
    "Customer's first name": "Klienta vārds", "optional, makes the email friendlier": "nav obligāti, padara e-pastu draudzīgāku",
    "What was the job?": "Kāds bija darbs?", "Show the QR code": "Rādīt QR kodu", "e.g. Wardrobe assembly": "piem., skapja montāža",
    "Next screen: they scan the code with their phone camera, or you email them the link.": "Nākamajā ekrānā: viņi noskenē kodu ar tālruņa kameru, vai jūs nosūtāt saiti e-pastā.",
    "See requests you've sent →": "Skatīt nosūtītos pieprasījumus →", "Review requests": "Atsauksmju pieprasījumi",
    "Who you've asked, and who's left a review.": "Kam esat lūdzis un kas ir atstājis atsauksmi.", "Ask someone": "Palūgt kādam",
    "No requests yet": "Vēl nav pieprasījumu", "Finish a job and tap \"Ask for a review\".": "Pabeidziet darbu un pieskarieties “Lūgt atsauksmi”.",
    /* transaction history + support */
    "Your plan, and everything HapiTech has done and covered for your website.": "Jūsu plāns un viss, ko HapiTech ir paveicis un sedzis jūsu vietnei.",
    "Transaction history": "Darījumu vēsture", "Month": "Mēnesis", "Search": "Meklēt", "Show all": "Rādīt visu",
    "e.g. hosting, 2025, HT-001…": "piem., mitināšana, 2025, HT-001…", "Show one month": "Rādīt vienu mēnesi", "Search transactions": "Meklēt darījumus",
    "Paid": "Apmaksāts", "Covered": "Segts", "Upcoming": "Gaidāms", "Due": "Jāmaksā", "Payment": "Maksājums",
    "To pay": "Jāmaksā", "Left to pay": "Atlikums", "Nothing for that month or search.": "Šim mēnesim vai meklējumam nekā nav.",
    "Total so far": "Kopā līdz šim", "Friends plan": "Draugu plāns", "Covered by HapiTech": "Sedz HapiTech",
    "Server maintenance": "Servera uzturēšana", "Security updates": "Drošības atjauninājumi", "SSL certificate renewal": "SSL sertifikāta atjaunošana",
    "Terms & privacy pages": "Noteikumu un privātuma lapas", "Payment received": "Maksājums saņemts", "Payment received (bank)": "Maksājums saņemts (banka)",
    "per month": "mēnesī", "per year": "gadā", "per 3 months": "par 3 mēnešiem",
    "Support HapiTech": "Atbalstīt HapiTech", "Other": "Cita summa", "Amount": "Summa",
    "🔒 Card or PayPal accepted, handled securely by PayPal.": "🔒 Pieņem karti vai PayPal, droši apstrādā PayPal.",
    "Hosting, maintenance, security, email and more": "Mitināšana, uzturēšana, drošība, e-pasts un vairāk",
    "☕ Support HapiTech": "☕ Atbalstīt HapiTech", "How much would you like to give?": "Cik vēlaties ziedot?", "← Back": "← Atpakaļ", "Not now": "Ne tagad", "Thank you!": "Paldies!", "Close": "Aizvērt",
    "Card or PayPal": "Karte vai PayPal", "Card, Apple Pay or Google Pay": "Karte, Apple Pay vai Google Pay",
    "Totally optional, and your plan stays the same either way. If you'd like to chip in towards the running costs, thank you!": "Pilnīgi brīvprātīgi, un jūsu plāns jebkurā gadījumā paliek tāds pats. Ja vēlaties piedalīties uzturēšanas izmaksās, paldies!",
    "That really helps keep everything running. Aaron's been told, so expect a thank-you from him too.": "Tas tiešām palīdz visu uzturēt. Ārons ir informēts, tāpēc gaidiet paldies arī no viņa.",
    /* history filter, work requests, project page */
    "Show": "Rādīt", "Everything": "Visu", "Show older": "Rādīt vecākus", "Show a year or month": "Rādīt gadu vai mēnesi",
    "e.g. hosting, HT-001…": "piem., mitināšana, HT-001…",
    "Need something doing?": "Vajag kaut ko izdarīt?", "+ Ask for something": "+ Palūgt kaut ko", "What kind?": "Kāda veida?",
    "A change to my website": "Izmaiņas manā vietnē", "A new feature or page": "Jauna funkcija vai lapa", "Rework something": "Pārstrādāt kaut ko",
    "Something else": "Kaut kas cits", "What would you like?": "Ko jūs vēlētos?", "Leave blank for a quote": "Atstājiet tukšu, lai saņemtu tāmi",
    "Received": "Saņemts", "Quote sent": "Tāme nosūtīta", "Booked in": "Ieplānots", "Done ✓": "Pabeigts ✓", "View quote": "Skatīt tāmi",
    "Changes, new features, a rework, anything extra for your website. Offer an amount if you like, or leave it blank and Aaron will send you a quote.": "Izmaiņas, jaunas funkcijas, pārstrāde, jebkas papildus jūsu vietnei. Ja vēlaties, piedāvājiet summu, vai atstājiet tukšu, un Ārons nosūtīs tāmi.",
    "Your new website is on its way": "Jūsu jaunā vietne ir ceļā", "Your website project": "Jūsu vietnes projekts",
    "Once it's live, this is where you'll change your wording, services and photos yourself. Until then, tell Aaron what you'd like and follow the progress here.": "Kad tā būs gatava, šeit paši varēsiet mainīt tekstus, pakalpojumus un foto. Līdz tam pastāstiet Āronam, ko vēlaties, un sekojiet progresam šeit.",
    "Dashboard set up": "Panelis iestatīts", "You're in ✓": "Jūs esat iekšā ✓", "Tell us what you need": "Pastāstiet, kas jums vajadzīgs",
    "Pages, features, photos, anything": "Lapas, funkcijas, foto, jebkas", "Build & preview": "Izveide un priekšskatījums",
    "Aaron builds it and shows you": "Ārons to izveido un parāda jums", "Go live": "Palaišana", "Then edit it all from here": "Tad visu rediģējiet šeit",
    "Pages, features, photos, ideas from other sites you like: add as many as you want. Offer an amount if you have a budget in mind, or leave it blank for a quote.": "Lapas, funkcijas, foto, idejas no citām vietnēm, kas jums patīk: pievienojiet, cik vēlaties. Piedāvājiet summu, ja jums ir budžets, vai atstājiet tukšu, lai saņemtu tāmi.",
    /* fragments around bold words (help, calendar) */
    "iPhone:": "iPhone:", "tap": "pieskarieties", ", then Settings → Calendar → Accounts → Add Account → Other →": ", tad Iestatījumi → Kalendārs → Konti → Pievienot kontu → Cits →",
    "Add Subscribed Calendar": "Pievienot abonētu kalendāru", ", and paste.": ", un ielīmējiet.", "Android / Google Calendar:": "Android / Google kalendārs:",
    "on a computer, open calendar.google.com → Other calendars →": "datorā atveriet calendar.google.com → Citi kalendāri →", "From URL": "No URL",
    ", and paste. It appears on your phone automatically.": ", un ielīmējiet. Tas automātiski parādīsies tālrunī.",
    "at the bottom of the screen (or \"Job done ✓\" on a job).": "ekrāna apakšā (vai “Darbs pabeigts ✓” pie darba).",
    "Show the customer the": "Parādiet klientam", "QR code": "QR kodu", ". They scan it with their phone camera and tap the stars.": ". Viņi to noskenē ar tālruņa kameru un pieskaras zvaigznēm.",
    "Quote requests from your website appear in": "Tāmju pieprasījumi no jūsu vietnes parādās sadaļā", ". Add phone enquiries with": ". Tālruņa pieprasījumus pievienojiet ar",
    "Open the job and": "Atveriet darbu un", ". They get an email and can accept it with one tap.": ". Viņi saņem e-pastu un var to apstiprināt ar vienu pieskārienu.",
    "with a date. They get a confirmation, and a reminder the day before.": "ar datumu. Viņi saņem apstiprinājumu un atgādinājumu dienu iepriekš.",
    "Afterwards tap": "Pēc tam pieskarieties", ", then": ", tad", "and follow \"Add to your phone's calendar\". It's set up once and updates by itself.": "un sekojiet “Pievienot tālruņa kalendāram”. To iestata vienreiz, un tas atjaunojas pats.",
    "in Safari tap the Share button, then": "Safari pieskarieties kopīgošanas pogai, tad", "Android:": "Android:", "on the banner, or the browser menu (⋮) →": "uz paziņojuma vai pārlūka izvēlnē (⋮) →",
    "Go to": "Atveriet", "to change your service text and photos. Changes appear within 10 minutes, and \"Undo\" puts back the last version.": "lai mainītu pakalpojumu tekstus un foto. Izmaiņas parādās 10 minūšu laikā, un “Atsaukt” atjauno iepriekšējo versiju.",
    "In": "Sadaļā", ", set \"Back on\". Your website shows a notice until then and booking requests pause.": ", iestatiet “Atpakaļ”. Līdz tam jūsu vietnē būs paziņojums, un rezervācijas tiks apturētas.",
    "→ Add a helper. They log in with their own email and can't see money or settings.": "→ Pievienot palīgu. Viņi piesakās ar savu e-pastu un neredz finanses vai iestatījumus.",
    "→ New post. Add a title like \"New bathroom in Tettenhall\" and a few photos. Posts with the town name help local people find you on Google.": "→ Jauns ieraksts. Pievienojiet virsrakstu, piem., “Jauna vannasistaba Tettenhallā”, un dažus foto. Ieraksti ar pilsētas nosaukumu palīdz vietējiem jūs atrast Google.",
    "Visits per day over the last 30 days": "Apmeklējumi dienā pēdējās 30 dienās",
    /* language switch */
    "Add": "Pievienot", "Language": "Valoda"
  };

  var MONTHS = { January: "janvāris", February: "februāris", March: "marts", April: "aprīlis", May: "maijs", June: "jūnijs",
    July: "jūlijs", August: "augusts", September: "septembris", October: "oktobris", November: "novembris", December: "decembris" };
  var MONTHS_GEN = { January: "janvāra", February: "februāra", March: "marta", April: "aprīļa", May: "maija", June: "jūnija",
    July: "jūlija", August: "augusta", September: "septembra", October: "oktobra", November: "novembra", December: "decembra" };
  var SHORT = { Jan: "janv.", Feb: "febr.", Mar: "marts", Apr: "apr.", May: "maijs", Jun: "jūn.", Jul: "jūl.", Aug: "aug.",
    Sep: "sept.", Oct: "okt.", Nov: "nov.", Dec: "dec." };
  function unit(n, one, many) { return n + " " + (n % 10 === 1 && n % 100 !== 11 ? one : many); }
  var AGO = { minute: ["minūtes", "minūtēm"], hour: ["stundas", "stundām"], day: ["dienas", "dienām"],
    week: ["nedēļas", "nedēļām"], month: ["mēneša", "mēnešiem"], year: ["gada", "gadiem"] };

  var P = [
    [/^Your offer \(£\)$/, "Jūsu piedāvājums (£)"], [/^All of (\d{4})$/, "Viss $1. gads"],
    [/^(\d+) requests?$/, "$1 pieprasījumi"], [/^(.+) · you offered (£[\d,.]+)$/, function (m, a, p) { return tr(a) + " · jūs piedāvājāt " + p; }],
    [/^Sent to Aaron\. (.+)$/, function (m, a) { return "Nosūtīts Āronam. " + (a.indexOf("quote") > -1 ? "Viņš atbildēs ar tāmi." : "Viņš to ar jums apstiprinās."); }],
    [/^Continue to (.+)$/, "Turpināt uz $1"], [/^You'll type the amount on (.+)\.$/, "Summu ievadīsiet $1."],
    [/^Receipt · download PDF$/, "Kvīts · lejupielādēt PDF"], [/^View · download PDF$/, "Skatīt · lejupielādēt PDF"],
    [/^(.+) \+ (\d+) more$/, function (m, a, n) { return tr(a) + " + vēl " + n; }],
    [/^(.+) & (.+)$/, function (m, a, b) { var x = tr(a), y = tr(b); return (x === a && y === b) ? null : x + " un " + y; }],
    [/^Friends plan: (.+)$/, function (m, a) { return "Draugu plāns: " + tr(a); }],
    [/^Covered by HapiTech: (.+)$/, function (m, a) { return "Sedz HapiTech: " + tr(a); }],
    [/^Donate £(.*)$/, "Ziedot £$1"],
    [/^(Hosting, maintenance, security, email and more) since (\w+) (\d{4}), covered by HapiTech\.$/, function (m, a, mo, y) { return "Mitināšanu, uzturēšanu, drošību, e-pastu un vairāk kopš " + y + ". gada " + (MONTHS_GEN[mo] || mo) + " sedz HapiTech."; }],
    [/^(\w{3}) (\d{4})$/, function (m, mo, y) { return SHORT[mo] ? SHORT[mo] + " " + y : null; }],
    [/^([\d.]+)★ average$/, "vidēji $1★"],
    [/^\/ (.+)$/, function (m, a) { return "/ " + tr(a); }],
    [/^Total (£[\d,.]+)$/, "Kopā $1"],
    [/^(\d+) from Google$/, "$1 no Google"],
    [/^(\d{1,2}) (Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)$/, function (m, d, mo) { return d + ". " + SHORT[mo]; }],
    [/^(.+) (£[\d,.]+)$/, function (m, a, p) { var t = tr(a); return t === a ? null : t + " " + p; }],
    [/^(.+) \| HapiTech$/, function (m, a) { return tr(a) + " | HapiTech"; }],
    [/^Hi (.+) 👋$/, "Sveiki, $1 👋"],
    [/^(\d+) characters left$/, function (m, n) { return "Atlikušas " + n + " rakstzīmes"; }],
    [/^(\d+) photos?$/, "$1 foto"], [/^(\d+) on your site$/, "$1 jūsu vietnē"], [/^(\d+) to edit$/, "$1 rediģējami"],
    [/^✏️ (\d+) of (\d+) sections changed by you$/, "✏️ Jūs mainījāt $1 no $2 sadaļām"],
    [/^(\d+) (minute|hour|day|week|month|year)s? ago$/, function (m, n, u) { return "pirms " + unit(+n, AGO[u][0], AGO[u][1]); }],
    [/^just now$/, "tikko"], [/^today$/, "šodien"], [/^yesterday$/, "vakar"],
    [/^Your last post was (.+)\.$/, function (m, a) { return "Jūsu pēdējais ieraksts bija " + tr(a) + "."; }],
    [/^(\d+) new reviews? this month\.$/, "Šomēnes jaunas atsauksmes: $1."],
    [/^([^()]+) \((\d+)\)$/, function (m, a, n) { var t = tr(a); return t === a ? null : t + " (" + n + ")"; }],
    [/^▲ (\d+)% on the 30 days before$/, "▲ $1% salīdzinot ar iepriekšējām 30 dienām"],
    [/^▼ (\d+)% on the 30 days before$/, "▼ $1% salīdzinot ar iepriekšējām 30 dienām"],
    [/^You're on our (.+)$/, function (m, a) { return "Jums ir mūsu " + tr(a).replace("plāns", "plāns"); }],
    [/^Email (.+) a confirmation$/, "Nosūtīt $1 apstiprinājumu e-pastā"],
    [/^View (.+)$/, "Skatīt $1"], [/^(.+) · Owner$/, "$1 · Īpašnieks"], [/^(.+) · Helper$/, "$1 · Palīgs"],
    [/^since (January|February|March|April|May|June|July|August|September|October|November|December) (\d{4})$/,
      function (m, mo, y) { return "kopš " + y + ". gada " + MONTHS_GEN[mo]; }],
    [/^(\d{1,2}) (January|February|March|April|May|June|July|August|September|October|November|December) (\d{4})$/,
      function (m, d, mo, y) { return y + ". gada " + d + ". " + MONTHS_GEN[mo]; }],
    [/^(January|February|March|April|May|June|July|August|September|October|November|December) (\d{4})$/,
      function (m, mo, y) { return y + ". gada " + MONTHS[mo]; }],
    [/^(£[\d,.]+) a (month|year) · (\w{3}) (\d{4}) to now \(([\d.]+) months\)$/,
      function (m, p, per, mo, y, n) { return p + (per === "month" ? " mēnesī" : " gadā") + " · no " + (SHORT[mo] || mo) + " " + y + " līdz šim (" + n + " mēn.)"; }],
    [/^(£[\d,.]+) a (month|year)$/, function (m, p, per) { return p + (per === "month" ? " mēnesī" : " gadā"); }],
    [/^Your hosting, email and domain since (\w+) (\d{4}), covered by HapiTech\. That's (£[\d,.]+) a month you don't pay\.$/,
      function (m, mo, y, p) { return "Jūsu mitināšanu, e-pastu un domēnu kopš " + y + ". gada " + (MONTHS_GEN[mo] || mo) + " sedz HapiTech. Tie ir " + p + " mēnesī, kas jums nav jāmaksā."; }],
    [/^(.+) of (.+) sections changed by you$/, null]
  ];

  function tr(s) {
    if (Object.prototype.hasOwnProperty.call(D, s)) return D[s];
    for (var i = 0; i < P.length; i++) {
      var re = P[i][0], to = P[i][1];
      if (!to) continue;
      var m = s.match(re);
      if (m) {
        var out = typeof to === "function" ? to.apply(null, m) : s.replace(re, to);
        if (out != null) return out;
      }
    }
    if (s.indexOf(" · ") > 0) {
      var seg = s.split(" · "), outSeg = seg.map(function (x) { return tr(x); });
      if (outSeg.join(" · ") !== s) return outSeg.join(" · ");
    }
    // a run of whole sentences we know ("No new reviews yet this month. Your last post was 2 days ago.")
    var parts = s.match(/[^.!?]+[.!?]+/g);
    if (parts && parts.length > 1 && parts.join("").length === s.length) {
      var all = parts.map(function (p) { var t = p.trim(); var r = tr(t); return r === t ? null : r; });
      if (all.every(function (x) { return x; })) return all.join(" ");
    }
    return s;
  }

  var ATTRS = ["placeholder", "title", "aria-label", "data-confirm"];
  function walk(node) {
    var w = document.createTreeWalker(node, NodeFilter.SHOW_TEXT), n;
    var list = [];
    while ((n = w.nextNode())) list.push(n);
    list.forEach(function (t) {
      var p = t.parentElement;
      if (!p || p.closest("script,style,textarea,[data-no-translate],.review__body,.site-card__text,.site-card__title")) return;
      var raw = t.nodeValue, trimmed = raw.replace(/\s+/g, " ").trim();
      if (!trimmed || !/[A-Za-z]/.test(trimmed)) return;
      var out = tr(trimmed);
      if (out !== trimmed) t.nodeValue = raw.replace(raw.trim(), out);
    });
    (node.querySelectorAll ? node.querySelectorAll("[placeholder],[title],[aria-label],[data-confirm]") : []).forEach(function (el) {
      ATTRS.forEach(function (a) {
        var v = el.getAttribute(a);
        if (v) { var o = tr(v.trim()); if (o !== v.trim()) el.setAttribute(a, o); }
      });
    });
  }

  window.htTranslate = tr;
  function run() {
    root.setAttribute("lang", "lv");
    document.title = tr(document.title);
    walk(document.body);
    done();
    var busy = false;
    new MutationObserver(function (muts) {
      if (busy) return; busy = true;
      muts.forEach(function (m) {
        if (m.type === "characterData") { walk(m.target.parentNode || document.body); }
        m.addedNodes && m.addedNodes.forEach(function (n) { if (n.nodeType === 1) walk(n); else if (n.nodeType === 3 && n.parentNode) walk(n.parentNode); });
      });
      busy = false;
    }).observe(document.body, { childList: true, subtree: true, characterData: true });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", run); else run();
  setTimeout(done, 1500);   // never leave the page hidden
})();
