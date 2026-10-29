"""Shared, bilingual transactional mail with a plain-text fallback."""
from django.template.loader import render_to_string


def verification_email(code, language='en-US'):
    zh = language == 'zh-CN'
    context = {
        'language': 'zh-CN' if zh else 'en',
        'eyebrow': '你的 POPOMO 账号' if zh else 'YOUR POPOMO ACCOUNT',
        'title': '离你的创作，只差一步。' if zh else 'One step closer to your creation.',
        'intro': '在网页中输入下方验证码，继续注册或登录。' if zh else 'Enter the code below to finish signing in or create your account.',
        'label': '你的验证码' if zh else 'YOUR SIGN-IN CODE',
        'code': code,
        'expiry': '10 分钟内有效 · 仅可使用一次' if zh else 'Expires in 10 minutes · Single use only',
        'note': '首次验证邮箱后将自动创建账号。注册赠送的 AI 次数以当前活动设置为准。' if zh else 'New here? Your account is created after email verification. Welcome AI generations follow the current signup offer.',
        'safety': '如果不是你本人操作，请忽略此邮件。请勿向他人分享验证码。' if zh else 'Didn’t request this? You can safely ignore this email. Never share your code with anyone.',
        'footer': '这是一封自动发送的账号邮件，请勿直接回复。' if zh else 'This is an automated account email. Please do not reply.',
        'tagline': '让日常，多一点自己。' if zh else 'A little more you.',
    }
    subject = 'POPOMO 登录验证码' if zh else 'Your POPOMO sign-in code'
    body = '\n\n'.join([context['intro'], f"{context['label']}: {code}", context['expiry'], context['note'], context['safety'], context['footer']])
    return subject, body, render_to_string('management_api/transactional_email.html', context)


def test_email():
    context = {
        'language': 'zh-CN', 'eyebrow': 'POPOMO · EMAIL CHECK',
        'title': '邮件连接已就绪。',
        'intro': '这是一封由 POPOMO 后台发出的测试邮件。收到此邮件，说明当前 SMTP 配置能够向这个邮箱发送邮件。',
        'label': 'SMTP 配置测试', 'status': '发送成功',
        'expiry': 'Your POPOMO email connection is working.',
        'note': '确认邮件显示正常后，即可在后台开启邮箱验证码。实际验证码邮件会使用相同的卡片样式，并根据用户选择显示英文或中文。',
        'safety': '此邮件用于测试，不包含登录验证码，也不会创建账号或扣除 AI 次数。',
        'footer': '这是一封自动发送的测试邮件，请勿直接回复。', 'tagline': 'A little more you.',
    }
    return ('POPOMO 邮件配置测试 / Email test', '\n\n'.join(context[k] for k in ['title','intro','expiry','note','safety','footer']),
            render_to_string('management_api/transactional_email.html', context))
