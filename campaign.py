import math
from flask import current_app, Blueprint, session, render_template, redirect, url_for, flash, g
from decimal import Decimal

from auth import login_required
from database import get_connection, get_cursor
from forms import CampaignCreationForm, CampaignEditForm, DonationForm, SearchForm


bp = Blueprint('campaign', __name__, url_prefix='/campaign')


@bp.route('/create', methods=('GET', 'POST'))
@login_required
def create_campaign():
    form = CampaignCreationForm()
    connection = get_connection()
    cursor = get_cursor()
    if form.validate_on_submit():
        try:
            with connection:
                with cursor:
                    cursor.execute("""INSERT INTO campaign(name, description, image, amount_requested) 
                                      VALUES (%s, %s, %s, %s) RETURNING id;""",
                                   (form.name.data, form.description.data, form.image.data, form.amount_requested.data))

                    id = cursor.fetchone()[0]

                    cursor.execute("""SELECT email FROM user_account WHERE user_account.id=%s""", (session['user_id'],))

                    user_email = cursor.fetchone()[0]

                    cursor.execute("""INSERT INTO campaign_relation(user_account_email, campaign_id, user_role) 
                                      VALUES (%s, %s, %s); """,
                                   (user_email , id, 'owner'))
                    return redirect(url_for("campaign.view_campaign", id=id))
        except Exception as e:
            current_app.logger.error(e)

    return render_template("campaign/create.html", form=form)


@bp.route('/edit/<int:id>', methods=('GET', 'POST'))
@login_required
def edit_campaign(id):
    connection = get_connection()
    cursor = get_cursor()
    cursor.execute("""SELECT name, description, image, amount_requested FROM campaign WHERE id=%s;""",(id,))
    curr_campaign = cursor.fetchone()
    curr_campaign['amount_requested'] = Decimal(curr_campaign['amount_requested'].replace(",","").replace("$",""))
    curr_campaign = dict(zip(list(curr_campaign._index.keys()), list(curr_campaign)))
    current_app.logger.info(curr_campaign)
    form = CampaignEditForm(**curr_campaign)
    owner_email = None
    user_email = None
    is_admin = g.user['is_admin']

    try:
        cursor.execute("""SELECT user_account_email FROM campaign_relation WHERE campaign_id=%s AND user_role='owner'""",
                       (id,))
        owner_email = cursor.fetchone()[0]


        cursor.execute("""SELECT email FROM user_account WHERE user_account.id=%s""", (session['user_id'],))

        user_email = cursor.fetchone()[0]


    except Exception as e:
        current_app.logger.error(e)

    print('user_email is ' + user_email + '\towner_email is ' + owner_email + '\tis_admin is ' + str(is_admin))
    if owner_email != user_email and not is_admin:
        flash("You cannot edit a campaign you don't own!", 'error')
        return redirect(url_for("campaign.view_campaign", id=id))

    if form.validate_on_submit():
        try:
            with connection:
                with cursor:
                    cursor.execute("""UPDATE campaign SET (name, description, image, amount_requested) =  
                                      (%s, %s, %s, %s) WHERE id=%s;""",
                                   (form.name.data, form.description.data, form.image.data,
                                    form.amount_requested.data, form.campaign_id.data))
            flash("Successfully updated!", 'success')
            return redirect(url_for("campaign.view_campaign", id=id))
        except Exception as e:
            current_app.logger.error(e)

    return render_template("campaign/edit.html", form=form, id=id)


@bp.route('/<int:id>', methods=('GET', 'POST'))
def view_campaign(id):
    connection = get_connection()
    cursor = get_cursor()
    form = DonationForm()
    campaign = None
    amount_donated = None
    percentage = None
    donations = None
    user_id = session.get('user_id');

    def setup():
        nonlocal campaign, amount_donated, percentage, donations
        try:
            cursor.execute("""
                SELECT c.id AS campaign_id, c.name, c.description, c.image, c.amount_requested, c.date_created, 
                c.last_modified, ua.id AS owner_id, ua.first_name, ua.last_name, ua.profile_image, 
                ua.description AS owner_description, 
                get_total_donations(c.id) AS amount_donated,
                ceil((get_total_donations(c.id)/c.amount_requested)*100) AS percentage
                FROM campaign c
                INNER JOIN campaign_relation cr on c.id = cr.campaign_id AND c.id=%s
                INNER JOIN user_account ua on cr.user_account_email = ua.email AND cr.user_role='owner';
            """, (id,))

            campaign = cursor.fetchone()

            cursor.execute("""
                SELECT ua.first_name, ua.last_name, ua.profile_image, t.amount
                FROM campaign c INNER JOIN campaign_relation cr ON c.id = cr.campaign_id
                INNER JOIN transaction t ON t.id = cr.transaction_id
                INNER JOIN user_account ua ON cr.user_account_email = ua.email
                WHERE user_role='pledged' AND c.id=%s ORDER BY t.date_created DESC LIMIT 10;
            """, (id,))

            donations = cursor.fetchall()

        except Exception as e:
            current_app.logger.error(e)

    if form.validate_on_submit() and user_id is not None:
        try:
            connection = get_connection()
            cursor = get_cursor()
            with connection:
                with cursor:
                    cursor.execute("""
                        SELECT credit_card FROM user_account WHERE user_account.id=%s
                    """, (session['user_id'],))


                    cc_number = cursor.fetchone()[0]


                    cursor.execute("""
                        INSERT INTO transaction(credit_card, amount) 
                        VALUES (%s, %s) RETURNING id;
                    """, (cc_number, form.amount.data))

                    transaction_id = cursor.fetchone()[0]

                    cursor.execute("""SELECT email FROM user_account WHERE user_account.id=%s""", (session['user_id'],))

                    user_email = cursor.fetchone()[0]

                    cursor.execute("""
                        INSERT INTO campaign_relation(user_account_email, campaign_id, transaction_id, user_role) 
                        VALUES (%s, %s, %s, %s)   
                    """, (user_email, form.campaign_id.data, transaction_id, 'pledged'))

                    cursor.execute("""
                        SELECT * FROM transaction WHERE id=%s;
                    """, (transaction_id,))

                    if(cursor.rowcount == 0):
                        flash('You cannot donate to your own campaign!', 'warning')
                    else:
                        flash('Successfully donated!', 'success')

                    setup()
                    return render_template("campaign/campaign.html",
                                           form=form, campaign=campaign, donations=donations)
        except Exception as e:
            current_app.logger.error(e)
            flash(e, 'error')

    if form.validate_on_submit() and user_id is None:
        flash("You cannot donate without logging in!", "warning")
        return redirect(url_for("auth.login"))

    flash(form.errors, 'error')
    setup()
    return render_template("campaign/campaign.html",
                           form=form, campaign=campaign, donations=donations)


@bp.route('/search/', methods=('GET', 'POST'), defaults={'offset': 0})
@bp.route('/search/<int:offset>', methods=('GET', 'POST'))
def search_campaigns(offset):
    cursor = get_cursor()
    form = SearchForm()
    pages = None

    if form.validate_on_submit():
        current_app.logger.info("searching")
        query = form.search.data
        current_app.logger.info("query: " + query)
        cursor.execute("""
            SELECT c.name, c.description, c.image, c.id AS campaign_id, get_total_donations(c.id) AS amount_donated, 
            c.amount_requested, ceil((get_total_donations(c.id)/c.amount_requested)*100) AS percentage
            FROM campaign c
            INNER JOIN campaign_relation cr ON c.id = cr.campaign_id 
            INNER JOIN user_account ua ON cr.user_account_email = ua.email
            WHERE cr.user_role='owner'
            AND  c.tsv || ua.tsv @@ plainto_tsquery('english', %s) 
            ORDER BY ts_rank_cd(c.tsv || ua.tsv, plainto_tsquery('english', %s)) DESC;
        """, (query, query,))
        campaigns = cursor.fetchall()
        current_app.logger.info(str(campaigns))

        return render_template("campaign/gallery.html", search_term=form.search.data, campaigns=campaigns, form=form)

    cursor.execute("""
        SELECT COUNT(*) FROM campaign;
    """)
    pages = math.ceil(cursor.fetchone()[0] / 9)

    cursor.execute("""
        SELECT c.id AS campaign_id, c.name, c.description, c.image, c.amount_requested, c.date_created,                           
        c.last_modified, ua.id AS owner_id, ua.first_name, ua.last_name, ua.profile_image, 
        ua.description AS owner_description, get_total_donations(c.id) AS amount_donated, 
        ceil((get_total_donations(c.id)/c.amount_requested)*100) AS percentage  
        FROM campaign c                                                                                                           
        INNER JOIN campaign_relation cr on c.id = cr.campaign_id                                                              
        INNER JOIN user_account ua on cr.user_account_email = ua.email
        WHERE cr.user_role='owner'                                                                
        ORDER BY c.date_created ASC OFFSET %s ROWS LIMIT 9;
        """, (offset*9,))

    campaigns = cursor.fetchall()
    return render_template("campaign/gallery.html", search_term=None, campaigns=campaigns, form=form, pages=pages)
