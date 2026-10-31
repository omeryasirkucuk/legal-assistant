Bir avukatın kendi yazdığı dilekçelerinden üslubunu öğrenmek için eklediği bir belgeyi okuyorsun. Belgenin ne olduğunu belirle:

- is_petition: belge avukatın ya da tarafın mahkemeye, icra dairesine veya karşı tarafa yazdığı bir dilekçe ya da ihtarname mi? Mahkeme kararı, tutanak, bilirkişi raporu, sözleşme, ödeme emri, vekaletname ya da başka bir belge ise false.
- petition_type: <petition_types> listesindeki kimlik; dilekçe değilse ya da listede yoksa "other".
- area: davanın hukuk alanı, <areas> listesindeki kimlik; belli değilse "other".
- case_kind: <case_kinds> listesindeki kimlik; dava bunlardan biri değilse "other". Listedeki ad davanın türünü dar tanımlar: örneğin "Çekişmeli boşanma davası" anlaşmalı boşanmayı kapsamaz.
- matter: davanın kısa tanımı, belgenin kendi diliyle (örneğin "anlaşmalı boşanma", "zina nedeniyle boşanma, nafaka ve tazminat", "kira alacağı için ödeme emrine itiraz"). Kişi adı, kimlik numarası, adres ya da tutar yazma.

Belgede yazanlara dayan; tahmin etme.
