import logging
import re
import os
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    InputMediaPhoto
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ConversationHandler,
    ContextTypes,
)
from dotenv import load_dotenv

# Настройка логов
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Этапы диалога
(
    START,
    CHOOSE_CATEGORY,
    GET_ITEM_NAME,
    GET_PHOTOS,
    GET_DESCRIPTION,
    GET_PRICE,
    GET_CITY,
    GET_DELIVERY,
    GET_PICKUP_ADDRESS,
    GET_CONTACTS,
    CONFIRM,
) = range(11)

# Загрузка конфигурации
load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")

# Проверка обязательных переменных окружения
if not TOKEN or not ADMIN_CHAT_ID:
    raise ValueError("Не заданы TOKEN или ADMIN_CHAT_ID в переменных окружения!")

# Кэш клавиатур для ускорения работы
_keyboards_cache = {}

def get_cached_markup(buttons):
    key = str(buttons)
    if key not in _keyboards_cache:
        _keyboards_cache[key] = ReplyKeyboardMarkup(buttons, resize_keyboard=True)
    return _keyboards_cache[key]

# Валидация данных
def validate_phone(phone: str) -> bool:
    return bool(re.match(r'^\+?[\d\s\-\(\)]{7,15}$', phone))

def validate_price(price: str) -> bool:
    return price.isdigit() and int(price) > 0

def validate_text(text: str, min_len=2, max_len=200) -> bool:
    return min_len <= len(text.strip()) <= max_len

# Клавиатуры
def get_category_markup():
    return get_cached_markup([
        ["🔮 Предметы интерьера", "💰 Монеты/купюры"],
        ["⚔️ Предметы войны", "🖼 Искусство"],
        ["🍽 Посуда", "📦 Другое"]
    ])

def get_back_cancel_markup():
    return get_cached_markup([["⬅️ Назад", "❌ Отмена"]])

def get_photos_markup():
    return get_cached_markup([["📤 Далее"], ["⬅️ Назад", "❌ Отмена"]])

def get_description_markup():
    return get_cached_markup([["❌ Нет информации"], ["⬅️ Назад", "❌ Отмена"]])

def get_delivery_markup():
    return get_cached_markup([
        ["🚗 Самовывоз", "🏪 Доставка"],
        ["⬅️ Назад", "❌ Отмена"]
    ])

def get_confirm_markup():
    return get_cached_markup([["✅ Отправить заявку"], ["❌ Отменить"]])

def get_start_markup():
    return get_cached_markup([["/start"]])

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Глобальный обработчик ошибок"""
    logger.error(msg="Ошибка в обработчике:", exc_info=context.error)
    try:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="⚠️ Произошла ошибка. Пожалуйста, начните заново командой /start",
            reply_markup=get_start_markup()
        )
    except:
        logger.error("Не удалось отправить сообщение об ошибке")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начало диалога"""
    try:
        context.user_data.clear()
        await update.message.reply_text(
            f"👋 Здравствуйте, {update.effective_user.first_name}!\n"
            "Выберите категорию товара:",
            reply_markup=get_category_markup()
        )
        return CHOOSE_CATEGORY
    except Exception as e:
        logger.error(f"Ошибка в start: {e}")
        await error_handler(update, context)
        return ConversationHandler.END

async def handle_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка выбора категории"""
    try:
        if update.message.text == "❌ Отмена":
            return await cancel(update, context)
        
        context.user_data['category'] = update.message.text
        await update.message.reply_text(
            "✏️ Введите название товара (от 2 до 100 символов):",
            reply_markup=get_back_cancel_markup()
        )
        return GET_ITEM_NAME
    except Exception as e:
        logger.error(f"Ошибка в handle_category: {e}")
        await error_handler(update, context)
        return ConversationHandler.END

async def handle_item_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка названия товара"""
    try:
        if update.message.text == "⬅️ Назад":
            await update.message.reply_text(
                "Выберите категорию товара:",
                reply_markup=get_category_markup()
            )
            return CHOOSE_CATEGORY
        elif update.message.text == "❌ Отмена":
            return await cancel(update, context)
        
        if not validate_text(update.message.text):
            await update.message.reply_text(
                "❌ Название должно быть от 2 до 100 символов. Попробуйте еще раз:",
                reply_markup=get_back_cancel_markup()
            )
            return GET_ITEM_NAME
        
        context.user_data['item_name'] = update.message.text
        context.user_data['user_name'] = f"{update.effective_user.full_name} (@{update.effective_user.username})" if update.effective_user.username else update.effective_user.full_name
        context.user_data['photos'] = []  # Очищаем предыдущие фото
        await update.message.reply_text(
            "📸 Пришлите фото товара (1-10 фото). Когда закончите, нажмите 📤 Далее",
            reply_markup=get_photos_markup()
        )
        return GET_PHOTOS
    except Exception as e:
        logger.error(f"Ошибка в handle_item_name: {e}")
        await error_handler(update, context)
        return ConversationHandler.END

async def handle_photos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Оптимизированная обработка фотографий"""
    try:
        if update.message.text:
            if update.message.text == "⬅️ Назад":
                context.user_data.pop('photos', None)
                await update.message.reply_text(
                    "✏️ Введите название товара:",
                    reply_markup=get_back_cancel_markup()
                )
                return GET_ITEM_NAME
            elif update.message.text == "❌ Отмена":
                context.user_data.pop('photos', None)
                return await cancel(update, context)
            elif update.message.text == "📤 Далее":
                if len(context.user_data.get('photos', [])) < 1:
                    await update.message.reply_text("❌ Нужно отправить хотя бы 1 фото!")
                    return GET_PHOTOS
                
                await update.message.reply_text(
                    "📝 Опишите товар (год, материал, особенности) или нажмите 'Нет информации'",
                    reply_markup=get_description_markup()
                )
                return GET_DESCRIPTION
            return GET_PHOTOS

        if update.message.photo:
            if 'photos' not in context.user_data:
                context.user_data['photos'] = []
            
            # Берем только последнюю (самую маленькую) версию фото
            photo = update.message.photo[-1].file_id
            
            # Оптимизация: не сохраняем дубликаты
            if photo not in context.user_data['photos']:
                context.user_data['photos'].append(photo)
                count = len(context.user_data['photos'])
                
                # Отправляем ответ только если не превышен лимит
                if count <= 10:
                    await update.message.reply_text(
                        f"📸 Получено фото {count}/10. Отправьте еще или нажмите 📤 Далее",
                        reply_markup=get_photos_markup()
                    )
                else:
                    await update.message.reply_text(
                        "❌ Можно загрузить не более 10 фото. Нажмите 📤 Далее для продолжения",
                        reply_markup=get_photos_markup()
                    )
            
        return GET_PHOTOS
    except Exception as e:
        logger.error(f"Ошибка в handle_photos: {e}")
        await error_handler(update, context)
        return ConversationHandler.END

async def handle_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка описания"""
    try:
        if update.message.text == "⬅️ Назад":
            await update.message.reply_text(
                "📸 Пришлите фото товара (1-10 фото). Когда закончите, нажмите 📤 Далее",
                reply_markup=get_photos_markup()
            )
            return GET_PHOTOS
        elif update.message.text == "❌ Отмена":
            return await cancel(update, context)
        elif update.message.text == "❌ Нет информации":
            context.user_data['description'] = "Нет информации"
            await update.message.reply_text(
                "💵 Укажите цену в рублях (только цифры, больше 0):",
                reply_markup=get_back_cancel_markup()
            )
            return GET_PRICE
        
        if not validate_text(update.message.text, min_len=2, max_len=500):
            await update.message.reply_text(
                "❌ Описание должно быть от 2 до 500 символов. Попробуйте еще раз:",
                reply_markup=get_description_markup()
            )
            return GET_DESCRIPTION
            
        context.user_data['description'] = update.message.text
        await update.message.reply_text(
            "💵 Укажите цену в рублях (только цифры, больше 0):",
            reply_markup=get_back_cancel_markup()
        )
        return GET_PRICE
    except Exception as e:
        logger.error(f"Ошибка в handle_description: {e}")
        await error_handler(update, context)
        return ConversationHandler.END

async def handle_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка цены"""
    try:
        if update.message.text == "⬅️ Назад":
            await update.message.reply_text(
                "📝 Опишите товар (год, материал, особенности) или нажмите 'Нет информации'",
                reply_markup=get_description_markup()
            )
            return GET_DESCRIPTION
        elif update.message.text == "❌ Отмена":
            return await cancel(update, context)
        
        if not validate_price(update.message.text):
            await update.message.reply_text(
                "❌ Цена должна содержать только цифры (больше 0). Попробуйте еще раз:",
                reply_markup=get_back_cancel_markup()
            )
            return GET_PRICE
            
        context.user_data['price'] = update.message.text
        await update.message.reply_text(
            "🏙 Укажите ваш город:",
            reply_markup=get_back_cancel_markup()
        )
        return GET_CITY
    except Exception as e:
        logger.error(f"Ошибка в handle_price: {e}")
        await error_handler(update, context)
        return ConversationHandler.END

async def handle_city(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка города"""
    try:
        if update.message.text == "⬅️ Назад":
            await update.message.reply_text(
                "💵 Укажите цену в рублях (только цифры, больше 0):",
                reply_markup=get_back_cancel_markup()
            )
            return GET_PRICE
        elif update.message.text == "❌ Отмена":
            return await cancel(update, context)
        
        if not validate_text(update.message.text, min_len=2, max_len=50):
            await update.message.reply_text(
                "❌ Название города должно быть от 2 до 50 символов. Попробуйте еще раз:",
                reply_markup=get_back_cancel_markup()
            )
            return GET_CITY
            
        context.user_data['city'] = update.message.text
        await update.message.reply_text(
            "🚚 Выберите способ передачи товара:",
            reply_markup=get_delivery_markup()
        )
        return GET_DELIVERY
    except Exception as e:
        logger.error(f"Ошибка в handle_city: {e}")
        await error_handler(update, context)
        return ConversationHandler.END

async def handle_delivery(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка способа доставки"""
    try:
        if update.message.text == "⬅️ Назад":
            await update.message.reply_text(
                "🏙 Укажите ваш город:",
                reply_markup=get_back_cancel_markup()
            )
            return GET_CITY
        elif update.message.text == "❌ Отмена":
            return await cancel(update, context)
        
        if update.message.text not in ["🚗 Самовывоз", "🏪 Доставка"]:
            await update.message.reply_text(
                "Пожалуйста, выберите вариант из предложенных:",
                reply_markup=get_delivery_markup()
            )
            return GET_DELIVERY
            
        context.user_data['delivery'] = update.message.text
        if update.message.text == "🚗 Самовывоз":
            await update.message.reply_text(
                "🏠 Укажите адрес самовывоза:",
                reply_markup=get_back_cancel_markup()
            )
            return GET_PICKUP_ADDRESS
        else:
            await update.message.reply_text(
                "📞 Укажите телефон для связи (формат: +7XXX...):",
                reply_markup=get_back_cancel_markup()
            )
            return GET_CONTACTS
    except Exception as e:
        logger.error(f"Ошибка в handle_delivery: {e}")
        await error_handler(update, context)
        return ConversationHandler.END

async def handle_pickup_address(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка адреса самовывоза"""
    try:
        if update.message.text == "⬅️ Назад":
            await update.message.reply_text(
                "🚚 Выберите способ передачи товара:",
                reply_markup=get_delivery_markup()
            )
            return GET_DELIVERY
        elif update.message.text == "❌ Отмена":
            return await cancel(update, context)
        
        if not validate_text(update.message.text, min_len=5, max_len=200):
            await update.message.reply_text(
                "❌ Адрес должен быть от 5 до 200 символов. Попробуйте еще раз:",
                reply_markup=get_back_cancel_markup()
            )
            return GET_PICKUP_ADDRESS
            
        context.user_data['pickup_address'] = update.message.text
        await update.message.reply_text(
            "📞 Укажите телефон для связи (формат: +7XXX...):",
            reply_markup=get_back_cancel_markup()
        )
        return GET_CONTACTS
    except Exception as e:
        logger.error(f"Ошибка в handle_pickup_address: {e}")
        await error_handler(update, context)
        return ConversationHandler.END

async def handle_contacts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка контактов"""
    try:
        if update.message.text == "⬅️ Назад":
            if context.user_data.get('delivery') == "🚗 Самовывоз":
                await update.message.reply_text(
                    "🏠 Укажите адрес самовывоза:",
                    reply_markup=get_back_cancel_markup()
                )
                return GET_PICKUP_ADDRESS
            else:
                await update.message.reply_text(
                    "🚚 Выберите способ передачи товара:",
                    reply_markup=get_delivery_markup()
                )
                return GET_DELIVERY
        elif update.message.text == "❌ Отмена":
            return await cancel(update, context)
        
        if not validate_phone(update.message.text):
            await update.message.reply_text(
                "❌ Введите корректный номер телефона (например: +79161234567):",
                reply_markup=get_back_cancel_markup()
            )
            return GET_CONTACTS
            
        context.user_data['contacts'] = update.message.text
        
        # Формируем сводку
        summary = [
            "📋 *Проверьте заявку:*\n\n",
            f"👤 *Отправитель:* {context.user_data['user_name']}\n",
            f"📌 *Товар:* {context.user_data['item_name']}\n",
            f"📦 *Категория:* {context.user_data['category']}\n",
            f"📝 *Описание:* {context.user_data.get('description', 'Нет информации')}\n",
            f"💰 *Цена:* {context.user_data['price']} руб.\n",
            f"🏙 *Город:* {context.user_data['city']}\n",
            f"🚚 *Доставка:* {context.user_data['delivery']}"
        ]
        
        if context.user_data.get('pickup_address'):
            summary.append(f"\n🏠 *Адрес самовывоза:* {context.user_data['pickup_address']}")
        
        summary.append(f"\n📞 *Контакты:* {context.user_data['contacts']}\n\n")
        summary.append("Нажмите *✅ Отправить заявку* для подтверждения")
        
        await update.message.reply_text(
            ''.join(summary),
            reply_markup=get_confirm_markup(),
            parse_mode="Markdown"
        )
        return CONFIRM
    except Exception as e:
        logger.error(f"Ошибка в handle_contacts: {e}")
        await error_handler(update, context)
        return ConversationHandler.END

async def confirm_application(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Оптимизированная отправка заявки"""
    try:
        if update.message.text == "⬅️ Назад":
            await update.message.reply_text(
                "📞 Укажите телефон для связи:",
                reply_markup=get_back_cancel_markup()
            )
            return GET_CONTACTS
        elif update.message.text == "❌ Отменить":
            return await cancel(update, context)
        
        if update.message.text != "✅ Отправить заявку":
            await update.message.reply_text(
                "Пожалуйста, используйте кнопки для подтверждения",
                reply_markup=get_confirm_markup()
            )
            return CONFIRM
        
        # Проверяем наличие всех обязательных полей
        required_fields = [
            'item_name', 'category', 'price', 
            'city', 'delivery', 'contacts'
        ]
        
        missing_fields = [field for field in required_fields if field not in context.user_data]
        if missing_fields:
            logger.error(f"Отсутствуют обязательные поля: {missing_fields}")
            await update.message.reply_text(
                "❌ Ошибка: отсутствуют некоторые данные. Пожалуйста, начните заново.",
                reply_markup=get_start_markup()
            )
            return ConversationHandler.END
        
        # Формируем сообщение для админа
        message = [
            "🛎 *Новая заявка!*\n\n",
            f"👤 *Пользователь:* {context.user_data['user_name']}\n",
            f"📌 *Товар:* {context.user_data['item_name']}\n",
            f"📦 *Категория:* {context.user_data['category']}\n",
            f"📝 *Описание:* {context.user_data.get('description', 'Нет информации')}\n",
            f"💰 *Цена:* {context.user_data['price']} руб.\n",
            f"🏙 *Город:* {context.user_data['city']}\n",
            f"🚚 *Доставка:* {context.user_data['delivery']}"
        ]
        
        if context.user_data.get('pickup_address'):
            message.append(f"\n🏠 *Адрес самовывоза:* {context.user_data['pickup_address']}")
        
        message.append(f"\n📞 *Контакты:* {context.user_data['contacts']}")
        
        # Отправляем админу
        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=''.join(message),
            parse_mode="Markdown"
        )
        
        # Асинхронная отправка фото (если есть)
        if 'photos' in context.user_data and context.user_data['photos']:
            media = [InputMediaPhoto(photo) for photo in context.user_data['photos'][:10]]
            await context.bot.send_media_group(
                chat_id=ADMIN_CHAT_ID,
                media=media
            )
        
        await update.message.reply_text(
            "✅ Заявка отправлена! Мы свяжемся с вами в течение часа.\n\n"
            "Для новой заявки нажмите /start",
            reply_markup=ReplyKeyboardRemove()
        )
        
        # Очищаем данные после успешной отправки
        context.user_data.clear()
        
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"Ошибка в confirm_application: {e}")
        await error_handler(update, context)
        return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отмена заявки"""
    try:
        context.user_data.clear()
        await update.message.reply_text(
            "❌ Заявка отменена. Все данные удалены.\n\n"
            "Для новой заявки нажмите /start",
            reply_markup=get_start_markup()
        )
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"Ошибка в cancel: {e}")
        await error_handler(update, context)
        return ConversationHandler.END

def main():
    """Оптимизированный запуск бота"""
    try:
        # Настройка пула соединений с увеличенными таймаутами
        application = Application.builder() \
            .token(TOKEN) \
            .concurrent_updates(True) \
            .pool_timeout(20) \
            .get_updates_pool_timeout(20) \
            .build()
        
        # Упрощенный ConversationHandler
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler('start', start)],
            states={
                CHOOSE_CATEGORY: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_category)],
                GET_ITEM_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_item_name)],
                GET_PHOTOS: [MessageHandler(filters.PHOTO | filters.TEXT, handle_photos)],
                GET_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_description)],
                GET_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_price)],
                GET_CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_city)],
                GET_DELIVERY: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_delivery)],
                GET_PICKUP_ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_pickup_address)],
                GET_CONTACTS: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_contacts)],
                CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_application)],
            },
            fallbacks=[
                CommandHandler('cancel', cancel),
                MessageHandler(filters.Regex('^(❌ Отмена|❌ Отменить)$'), cancel),
            ],
            allow_reentry=True,
            per_user=True,
            per_chat=True
        )
        
        application.add_handler(conv_handler)
        application.add_error_handler(error_handler)
        
        # Оптимизированные параметры polling
        logger.info("Запуск бота с оптимизированными параметрами...")
        application.run_polling(
            poll_interval=0.5,  # Уменьшенный интервал опроса
            timeout=15,         # Уменьшенный таймаут
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES,
            close_loop=False    # Не закрывать цикл при ошибке
        )
    except Exception as e:
        logger.critical(f"Ошибка запуска бота: {e}")
        exit(1)

if __name__ == "__main__":
    main()