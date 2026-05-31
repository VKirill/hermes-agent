"""Telegram topic icon constants — free-account-validated emoji IDs."""

# All 28 emoji IDs from getForumTopicIconStickers (free Telegram accounts).
# Each tuple: (custom_emoji_id, display_label)
TELEGRAM_FREE_TOPIC_ICONS = [
    ("5312016608254762256", "1. ⚡ lightning - bugs, fixes, debugging"),
    ("5350554349074391003", "2. 💻 laptop - code, programming"),
    ("5379748062124056162", "3. ❗ exclamation - errors, warnings"),
    ("5348227245599105972", "4. 💼 briefcase - setup, infrastructure"),
    ("5309965701241379366", "5. 🔍 magnifying glass - testing, review"),
    ("5373251851074415873", "6. 📝 memo - writing, docs, notes"),
    ("5434144690511290129", "7. 📰 newspaper - reports, news, summaries"),
    ("5350481781306958339", "8. 📚 books - research, learning"),
    ("5377316857231450742", "9. ❓ question mark - questions, help"),
    ("5312536423851630001", "10. 💡 lightbulb - ideas, concepts"),
    ("5310039132297242441", "11. 🎨 palette - design, art, creative"),
    ("5368653135101310687", "12. 🎬 clapper - video, film"),
    ("5310045076531978942", "13. 🎵 music note - audio, music"),
    ("5377544228505134960", "14. 🎙️ microphone - podcasts, transcripts"),
    ("5350305691942788490", "15. 📈 chart - data, analytics, metrics"),
    ("5309832892262654231", "16. 🤖 robot - AI, bots, automation"),
    ("5433614043006903194", "17. 📅 calendar - planning, scheduling"),
    ("5357315181649076022", "18. 📁 folder - projects, files"),
    ("5417915203100613993", "19. 💬 speech bubble - chat, discussion"),
    ("5309984423003823246", "20. 📣 megaphone - announcements"),
    ("5309950797704865693", "21. 🎮 gamepad - gaming, play"),
    ("5350452584119279096", "22. 💰 money bag - finance, costs"),
    ("5312486108309757006", "23. 🏠 house - home, personal"),
    ("5350406176997646350", "24. 🍣 sushi - food, recipes"),
    ("5310228579009699834", "25. 🎉 party popper - celebration"),
    ("5312315739842026755", "26. 🏆 trophy - success, achievement"),
    ("5312322066328853156", "27. 🚗 car - travel, transportation"),
    ("5350307998340226571", "28. 🩺 stethoscope - medical, health"),
]

# LLM prompt fragment listing all icons by number
TOPIC_ICON_OPTIONS_TEXT = "\n".join(
    label for _, label in TELEGRAM_FREE_TOPIC_ICONS
)

# Reverse lookup: 1-indexed number → custom_emoji_id
TOPIC_ICON_BY_INDEX = {
    i + 1: emoji_id for i, (emoji_id, _) in enumerate(TELEGRAM_FREE_TOPIC_ICONS)
}