document.addEventListener('DOMContentLoaded', () => {
    // --- Modal Logic ---
    const userWrapper = document.querySelector('#userWrapper');
    const adminWrapper = document.querySelector('#adminLogin');
    const overlay = document.querySelector('.overlay');

    const loginLink = document.querySelector('.login-link');
    const registerLink = document.querySelector('.register-link');
    const userBtnPopup = document.querySelector('.btnLogin-popup');
    const adminTrigger = document.querySelector('.admin-login');
    const closeButtons = document.querySelectorAll('.icon-close');

    registerLink?.addEventListener('click', () => userWrapper?.classList.add('active'));
    loginLink?.addEventListener('click', () => userWrapper?.classList.remove('active'));
    userBtnPopup?.addEventListener('click', () => {
        userWrapper?.classList.add('active-popup');
        overlay?.classList.add('active');
    });
    adminTrigger?.addEventListener('click', () => {
        adminWrapper?.classList.add('active-popup');
        overlay?.classList.add('active');
    });

    closeButtons.forEach(btn =>
        btn.addEventListener('click', () => {
            userWrapper?.classList.remove('active-popup', 'active');
            adminWrapper?.classList.remove('active-popup');
            overlay?.classList.remove('active');
        })
    );

    overlay?.addEventListener('click', () => {
        userWrapper?.classList.remove('active-popup', 'active');
        adminWrapper?.classList.remove('active-popup');
        overlay?.classList.remove('active');
    });

    // --- Flash Messages ---
    const flashMessages = document.querySelector('.flash-container');
    if (flashMessages) {
        flashMessages.style.display = 'block';

        setTimeout(() => {
            const flashMessage = flashMessages.querySelector('.flash-message');
            if (flashMessage) {
                flashMessage.style.transition = 'opacity 1s ease-out';
                flashMessage.style.opacity = 0;

                flashMessage.addEventListener('transitionend', () => {
                    flashMessage.remove();
                });
            }
        }, 3000);
    }

    // --- Enroll Button ---
    document.querySelector('#enrollBtn')?.addEventListener('click', function () {
        this.disabled = true;
        this.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Enrolling...';
    });
});

