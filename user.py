from auth import login_required
from cs2102 import get_cursor, get_connection
from flask import Blueprint, current_app, render_template, flash, redirect, url_for
from forms import EditUserProfileForm

bp = Blueprint('user', __name__, url_prefix='/user')


@bp.route('/<int:id>', methods=('GET', 'POST'))
@login_required
def view_edit_user_profile(id):
    connection = get_connection()
    cursor = get_cursor()
    user_info = None
    campaigns = None

    try:
        cursor.execute("""SELECT up.first_name, up.last_name, up.address1, up.address2, up.postal_code, up.phone_number, up.profile_image, up.description, up.credit_card
                  FROM user_profile up
                  WHERE up.id=%s;""", (id,))
        user_info = cursor.fetchone()
        cursor.execute("""
                SELECT c.id, c.name, c.image AS campaign_image, c.date_created 
                FROM user_profile up INNER JOIN campaign_relation cr ON cr.user_account_id = up.user_account_id
                INNER JOIN campaign c ON c.id = cr.campaign_id
                WHERE up.user_account_id=%s AND user_role='owner' ORDER BY c.date_created DESC LIMIT 10;
            """, (id,))
        campaigns = cursor.fetchall()

    except Exception as e:
        current_app.logger.error(e)

    curr_user = dict(zip(list(user_info._index.keys()), list(user_info)))
    current_app.logger.info(curr_user)
    form = EditUserProfileForm(**curr_user)

    if form.validate_on_submit():
        try:
            with connection:
                with cursor:
                    cursor.execute("""UPDATE user_profile
                                      SET (first_name, last_name, address1, address2, postal_code, 
                                           phone_number, profile_image, description, credit_card) =  
                                          (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                                      WHERE id=%s;""", (form.first_name.data, form.last_name.data, form.address1.data,
                                                        form.address2.data, form.postal_code.data, form.phone_number.data,
                                                        form.profile_image.data, form.description.data, form.credit_card.data, id))
            flash("Successfully updated!", 'success')
            return redirect(url_for("user.view_edit_user_profile", id=id))

        except Exception as e:
            current_app.logger.error(e)

    return render_template("user/user_profile.html", user_info=user_info, form=form, id=id, campaigns=campaigns)


@bp.route('/public_profile/<int:id>', methods=('GET',))
def view_public_profile(id):
    connection = get_connection()
    cursor = get_cursor()
    public_profile = None
    campaign_donated = None
    campaign_created = None

    try:
        cursor.execute("""SELECT up.profile_image, up.first_name, up.last_name, 
        up.description, ua.email AS owner_email
        FROM user_profile up INNER JOIN user_account ua ON up.user_account_id = ua.id
        WHERE up.user_account_id=%s;
        """, (id,))

        public_profile = cursor.fetchone()

        cursor.execute("""
                SELECT c.id, c.name, c.image AS campaign_image, c.date_created 
                FROM user_profile up INNER JOIN campaign_relation cr ON cr.user_account_id = up.user_account_id
                INNER JOIN campaign c ON c.id = cr.campaign_id
                WHERE up.user_account_id=%s AND user_role='owner' ORDER BY c.date_created DESC LIMIT 10;
            """, (id,))

        campaign_created = cursor.fetchall()

        cursor.execute("""
                SELECT c.id, c.name, c.image AS campaign_image, c.date_created
                FROM user_profile up INNER JOIN campaign_relation cr ON cr.user_account_id = up.user_account_id
                INNER JOIN campaign c ON c.id = cr.campaign_id
                WHERE up.user_account_id=%s AND user_role='pledged' ORDER BY c.date_created DESC LIMIT 10;
        """, (id,))

        campaign_donated = cursor.fetchall()

    except Exception as e:
        current_app.logger.error(e)

    return render_template("user/public_profile.html", public_profile=public_profile,
                           campaign_created=campaign_created, campaign_donated=campaign_donated)
