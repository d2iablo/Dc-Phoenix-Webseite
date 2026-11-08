-- =====================================================================
-- DC Phönix Durmersheim – Spielerkonten (Supabase)
-- Einmal im Supabase-Dashboard unter "SQL Editor" einfügen und "Run" drücken.
-- Sicher mehrfach ausführbar.
-- =====================================================================

-- 1) Tabelle für die Spielerprofile (eine Zeile pro Konto)
create table if not exists public.profiles (
  id                    uuid primary key references auth.users (id) on delete cascade,
  email                 text,
  spielername           text not null,                 -- genau so wie in der BDL-Statistik
  muss_passwort_aendern boolean not null default true,

  -- Angaben, die der Spieler selbst eintragen darf
  spitzname             text    check (char_length(spitzname)    <= 40),
  pfeile                text    check (char_length(pfeile)       <= 80),
  gewicht_gramm         numeric(4,1) check (gewicht_gramm between 10 and 60),
  bestes_finish         smallint check (bestes_finish between 2 and 170),
  bester_short_leg      smallint check (bester_short_leg between 9 and 60),
  herkunft              text    check (char_length(herkunft)     <= 60),
  geburtstag            date    check (geburtstag >= date '1900-01-01'),
  geburtsort            text    check (char_length(geburtsort)   <= 60),
  nationalitaet         text    check (char_length(nationalitaet) <= 40),

  -- Pro Feld: darf es auf der öffentlichen Webseite stehen? (standardmäßig nein)
  zeige_spitzname       boolean not null default false,
  zeige_pfeile          boolean not null default false,
  zeige_gewicht         boolean not null default false,
  zeige_bestes_finish   boolean not null default false,
  zeige_bester_short_leg boolean not null default false,
  zeige_herkunft        boolean not null default false,
  zeige_geburtstag      boolean not null default false,   -- öffentlich nur Tag und Monat
  zeige_geburtsort      boolean not null default false,
  zeige_nationalitaet   boolean not null default false,

  -- Erinnerungs-Mails zum nächsten Spiel
  erinnerung            text not null default '1' check (erinnerung in ('keine','1','3','beide')),

  erstellt              timestamptz not null default now(),
  geaendert             timestamptz not null default now()
);

-- 2) Zeilensicherheit: jeder sieht und ändert nur sein eigenes Profil,
--    und ändern erst, nachdem das Startpasswort ersetzt wurde.
alter table public.profiles enable row level security;
alter table public.profiles force row level security;

drop policy if exists "eigenes Profil lesen" on public.profiles;
create policy "eigenes Profil lesen" on public.profiles
  for select to authenticated
  using (id = (select auth.uid()));

drop policy if exists "eigenes Profil aendern" on public.profiles;
create policy "eigenes Profil aendern" on public.profiles
  for update to authenticated
  using      (id = (select auth.uid()) and muss_passwort_aendern = false)
  with check (id = (select auth.uid()) and muss_passwort_aendern = false);

-- 3) Spaltenrechte: nur diese Felder darf ein Spieler überhaupt schreiben.
--    Name, E-Mail, Passwort-Pflicht-Flag usw. kann nur der Admin (du) ändern.
revoke all on public.profiles from anon, authenticated;
grant select on public.profiles to authenticated;
grant update (
  spitzname, pfeile, gewicht_gramm, bestes_finish, bester_short_leg,
  herkunft, geburtstag, geburtsort, nationalitaet,
  zeige_spitzname, zeige_pfeile, zeige_gewicht, zeige_bestes_finish,
  zeige_bester_short_leg, zeige_herkunft, zeige_geburtstag, zeige_geburtsort,
  zeige_nationalitaet, erinnerung
) on public.profiles to authenticated;

-- 4) Prüfungen und Zeitstempel
create or replace function public.profiles_vor_update()
returns trigger language plpgsql set search_path = '' as $$
begin
  if new.geburtstag is not null and new.geburtstag > current_date then
    raise exception 'Geburtstag liegt in der Zukunft';
  end if;
  new.geaendert := now();
  return new;
end $$;

drop trigger if exists profiles_vor_update on public.profiles;
create trigger profiles_vor_update before update on public.profiles
  for each row execute function public.profiles_vor_update();

-- 5) Profil automatisch anlegen, wenn du im Dashboard ein Konto erstellst
create or replace function public.neues_konto()
returns trigger language plpgsql security definer set search_path = '' as $$
begin
  insert into public.profiles (id, email, spielername)
  values (new.id, new.email, coalesce(nullif(new.raw_user_meta_data ->> 'spielername', ''), split_part(new.email, '@', 1)))
  on conflict (id) do nothing;
  return new;
end $$;

drop trigger if exists neues_konto on auth.users;
create trigger neues_konto after insert on auth.users
  for each row execute function public.neues_konto();

create or replace function public.konto_email_aktualisieren()
returns trigger language plpgsql security definer set search_path = '' as $$
begin
  update public.profiles set email = new.email where id = new.id;
  return new;
end $$;

drop trigger if exists konto_email_aktualisieren on auth.users;
create trigger konto_email_aktualisieren after update of email on auth.users
  for each row execute function public.konto_email_aktualisieren();

-- 6) Erst-Login: Der Spieler bestätigt, dass er sein Passwort geändert hat.
create or replace function public.passwort_geaendert()
returns void language sql security definer set search_path = '' as $$
  update public.profiles set muss_passwort_aendern = false where id = (select auth.uid());
$$;
revoke all on function public.passwort_geaendert() from public, anon;
grant execute on function public.passwort_geaendert() to authenticated;

-- 7) Öffentliche Sicht: nur Felder, die der Spieler freigegeben hat.
--    Wird NICHT über die offene API ausgeliefert, sondern nur vom automatischen
--    Update (mit dem geheimen service_role-Schlüssel) abgeholt.
create or replace view public.oeffentliche_profile with (security_invoker = false) as
select
  spielername,
  case when zeige_spitzname        then spitzname end                         as spitzname,
  case when zeige_pfeile           then pfeile end                            as pfeile,
  case when zeige_gewicht          then gewicht_gramm end                     as gewicht_gramm,
  case when zeige_bestes_finish    then bestes_finish end                     as bestes_finish,
  case when zeige_bester_short_leg then bester_short_leg end                  as bester_short_leg,
  case when zeige_herkunft         then herkunft end                          as herkunft,
  case when zeige_geburtstag       then to_char(geburtstag, 'DD.MM.') end     as geburtstag,
  case when zeige_geburtsort       then geburtsort end                        as geburtsort,
  case when zeige_nationalitaet    then nationalitaet end                     as nationalitaet
from public.profiles
where muss_passwort_aendern = false;

revoke all on public.oeffentliche_profile from anon, authenticated;

-- 8) Protokoll bereits verschickter Erinnerungen (damit niemand doppelt eine Mail bekommt)
create table if not exists public.mail_log (
  user_id   uuid not null references auth.users (id) on delete cascade,
  spiel     text not null,
  art       text not null,
  gesendet  timestamptz not null default now(),
  primary key (user_id, spiel, art)
);
alter table public.mail_log enable row level security;
revoke all on public.mail_log from anon, authenticated;
