import os
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from google import genai
from google.genai.errors import APIError

# --- 1. कॉन्फ़िगरेशन (Environment Variables से Keys प्राप्त करें) ---
# ये Keys Render पर Environment Variables के रूप में सेट की जाएंगी
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# Render Webhook/Always Alive के लिए आवश्यक
PORT = int(os.environ.get('PORT', 8080))
WEBHOOK_URL = os.environ.get('WEBHOOK_URL')

# Gemini क्लाइंट को इनिशियलाइज़ करें
client = None
model = 'gemini-2.5-flash'

if GEMINI_API_KEY:
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
    except Exception as e:
        print(f"Error initializing Gemini Client: {e}")
        client = None
else:
    print("GEMINI_API_KEY not found. AI functionality will be disabled.")

# --- 2. AI प्रश्न जनरेशन फंक्शन ---
def generate_quiz_data(topic):
    """Gemini AI का उपयोग करके प्रश्न, विकल्प, उत्तर और स्पष्टीकरण जनरेट करें।"""
    if not client:
        return None

    if topic == 'English':
        # --- A. English-Only Prompt for English Quiz ---
        json_format = """
        {
            "question_en": "The generated MCQ text.",
            "options": ["Option A", "Option B", "Option C", "Option D"],
            "correct_answer_en": "The exact English text of the correct option (e.g., Option A)",
            "explanation_en": "A detailed explanation in English."
        }
        """
        lang_instruction = "The entire output must be in English ONLY."
    else:
        # --- B. Bilingual (English + Hindi) Prompt for G.K. Quiz ---
        json_format = """
        {
            "question_en": "The generated MCQ text in English.",
            "question_hi": "उत्पन्न किया गया MCQ प्रश्न हिंदी में।",
            "options": [
                {"en": "English Option 1", "hi": "हिंदी विकल्प 1"},
                {"en": "English Option 2", "hi": "हिंदी विकल्प 2"},
                {"en": "English Option 3", "hi": "हिंदी विकल्प 3"},
                {"en": "English Option 4", "hi": "हिंदी विकल्प 4"}
            ],
            "correct_answer_en": "The exact English text of the correct option (e.g., English Option 1)",
            "explanation_en": "A detailed explanation in English.",
            "explanation_hi": "एक विस्तृत स्पष्टीकरण हिंदी में।"
        }
        """
        lang_instruction = "The output MUST be bilingual (English and Hindi). The 'options' must be an array of 4 objects, each containing 'en' (English text) and 'hi' (Hindi text)."

    prompt = f"""
    Act as an expert question setter for the SSC CGL/CHSL exam. Your task is to generate one random Multiple Choice Question (MCQ) on the topic: **{topic}**.
    The question should be challenging and unique.
    
    {lang_instruction}
    
    The output must be strictly in the following JSON format ONLY:
    {json_format}
    Ensure the JSON is perfectly valid and self-contained.
    """
    
    try:
        response = client.models.generate_content(
            model=model,
            contents=prompt
        )
        
        # AI आउटपुट को JSON में पार्स करें
        quiz_data = json.loads(response.text.strip())
        return quiz_data
        
    except (APIError, json.JSONDecodeError, Exception) as e:
        print(f"Error generating content or parsing JSON: {e}")
        return None

# --- 3. Telegram कमांड हैंडलर (/start) ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Welcome मैसेज और मुख्य विषय बटन भेजें।"""
    keyboard = [
        [InlineKeyboardButton("📚 English", callback_data='quiz_start_English')],
        [InlineKeyboardButton("🧠 G.K. (द्विभाषी)", callback_data='quiz_start_GK')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "👋 **Welcome to Test bot for SSC exams!**\n\n"
        "कृपया अपनी क्विज़ का विषय चुनें:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

# --- 4. प्रश्न भेजने का मुख्य फंक्शन ---
async def send_new_question(update: Update, context: ContextTypes.DEFAULT_TYPE, topic: str) -> None:
    """AI से प्रश्न जनरेट करें और Telegram पर भेजें।"""
    
    await update.effective_chat.send_message("⌛ नया प्रश्न जनरेट किया जा रहा है...")
    quiz_data = generate_quiz_data(topic)
    
    if not quiz_data:
        await update.effective_chat.send_message(
            "❌ क्षमा करें, AI प्रश्न जनरेट नहीं कर पाया। कृपया **Next Question** दबाकर फिर से प्रयास करें।"
        )
        return

    # डेटा को Context में स्टोर करें
    context.user_data['current_quiz_data'] = quiz_data
    context.user_data['current_topic'] = topic
    
    keyboard = []
    
    if topic == 'English':
        # English-Only Display Logic
        question_text = quiz_data['question_en']
        options = quiz_data.get('options', [])
        
        message_text = f"**{topic} Quiz**\n\nQ: {question_text}"
        
        for option_text in options:
            callback_data = f"answer_{option_text}"
            keyboard.append([InlineKeyboardButton(option_text, callback_data=callback_data)])
            
    else:
        # G.K. (Bilingual) Display Logic
        question_en = quiz_data.get('question_en', 'N/A')
        question_hi = quiz_data.get('question_hi', 'N/A')
        options_list = quiz_data.get('options', [])

        message_text = f"**{topic} Quiz (द्विभाषी)**\n\n**Q (Eng):** {question_en}\n**Q (हिं):** {question_hi}\n\n**-- Options / विकल्प --**"
        
        for opt_obj in options_list:
            # Create a clear bilingual button label
            bilingual_label = f"🇬🇧 {opt_obj['en']} | 🇮🇳 {opt_obj['hi']}"
            # Send English text as callback data for comparison
            callback_data = f"answer_{opt_obj['en']}"
            keyboard.append([InlineKeyboardButton(bilingual_label, callback_data=callback_data)])

    reply_markup = InlineKeyboardMarkup(keyboard)

    # प्रश्न भेजें
    await update.effective_chat.send_message(
        message_text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

# --- 5. Callback (बटन प्रेस) हैंडलर ---
async def handle_button_press(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """जब यूजर कोई बटन दबाता है, तो यह फंक्शन चलता है।"""
    query = update.callback_query
    await query.answer() 

    data = query.data
    
    # 5.1 विषय चयन हैंडलिंग (quiz_start_...)
    if data.startswith('quiz_start_'):
        topic = data.split('_')[2]
        await query.edit_message_text(f"🚀 **{topic}** क्विज़ शुरू हो रही है...", parse_mode='Markdown')
        await send_new_question(update, context, topic)
        return

    # 5.2 उत्तर चयन हैंडलिंग (answer_...)
    if data.startswith('answer_'):
        user_answer_text = data.split('answer_')[1]
        quiz_data = context.user_data.get('current_quiz_data')

        if not quiz_data:
            await query.edit_message_text("❌ क्विज़ डेटा नहीं मिला। कृपया /start दबाकर पुनः शुरू करें।")
            return

        correct_answer = quiz_data['correct_answer_en']
        topic = context.user_data.get('current_topic', 'SSC')

        # 5.2.1 उत्तर की जाँच
        is_correct = (user_answer_text == correct_answer)

        response_text = f"**आपका उत्तर:** {user_answer_text}\n"
        
        if is_correct:
            response_text += "✅ **Correct Answer!**\n\n"
        else:
            response_text += f"❌ **Wrong Answer!**\n"
            response_text += f"**सही उत्तर:** {correct_answer}\n\n"

        # 5.2.2 Explanation Logic (Bilingual for GK, English for English)
        if topic == 'English':
            explanation_en = quiz_data.get('explanation_en', 'No explanation available.')
            response_text += f"**💡 Explanation:**\n*{explanation_en}*"
        else:
            explanation_en = quiz_data.get('explanation_en', 'No English explanation available.')
            explanation_hi = quiz_data.get('explanation_hi', 'हिंदी में कोई स्पष्टीकरण उपलब्ध नहीं है।')
            
            response_text += f"**💡 Explanation (Eng):**\n*{explanation_en}*\n\n"
            response_text += f"**💡 स्पष्टीकरण (हिं):**\n*{explanation_hi}*"

        # 'Next Question' बटन
        next_q_keyboard = [[InlineKeyboardButton("➡️ Next Question", callback_data=f'quiz_start_{topic}')]]
        reply_markup = InlineKeyboardMarkup(next_q_keyboard)

        # पुराने प्रश्न वाले मैसेज को उत्तर और स्पष्टीकरण से बदलें
        await query.edit_message_text(
            response_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return

# --- 6. मुख्य Webhook फंक्शन (Render Deployment के लिए) ---
def main() -> None:
    """बॉट को Webhook मोड में शुरू करें।"""
    if not TELEGRAM_BOT_TOKEN or not WEBHOOK_URL:
        print("CRITICAL ERROR: TELEGRAM_BOT_TOKEN or WEBHOOK_URL not set.")
        return

    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # हैंडलर जोड़ें
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(handle_button_press))

    print("Bot started via Webhook...")

    # Webhook को रन करें
    application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        # सुरक्षा के लिए URL Path में Token का उपयोग करें
        url_path=TELEGRAM_BOT_TOKEN, 
        webhook_url=f"{WEBHOOK_URL}/{TELEGRAM_BOT_TOKEN}"
    )

if __name__ == "__main__":
    main()
