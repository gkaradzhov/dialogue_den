$(function() {
    var socket = io.connect('https://' + document.domain, {autoConnect: true,  transports: ["websocket", "polling"], upgrade: true, forceNew: true});

    var room_id = $('input#chat_id').val();
    var timer = null;
    var room_status = $('#room_status').val();
    var sound = document.getElementById("audio");
    var user_name = $('input#user_name').val();
    var global_user_id = $('input#user_id').val();
    var current_user_type = $('#user_type').val();


    if (current_user_type == 'human_delibot'){
        $('#message').prop('disabled', true);
        $('#msg_submit').prop('disabled', true);
    }

    if (room_status == ROUTING_TIMER_STARTED || room_status == READY_TO_START){
        $.notify("The group phase of the game will start soon! Please submit your card selection. Once everyone does so, the game will start! (click to close)",  {autoHide: false, className: 'info'});
        activityWatcher(wakeup, kick);
        sound.play();

        if (room_status == ROUTING_TIMER_STARTED){
                var user_status = $('input#user_status').val();
                var start_time = $('input#start_time').val();
                var now = new Date();
                var after_x_min = new Date(now);
                after_x_min.setMinutes(now.getMinutes() + parseInt(start_time));
                var countDownDate = after_x_min.getTime();
                $('#game_start_timer').removeClass('hidden');
                var timer = setInterval(function(){start_timer(countDownDate, true, "Waiting for player",
                 function(){
                    socket.emit('response', {
                                user_id: global_user_id,
                                user_name: user_name,
                                type: ROUTING_TIMER_ELAPSED,
                                room: room_id,
                                user_status: user_status,
                                user_type: current_user_type,
                                message: ''
                            });
                        clearInterval(timer);
                    })}, 1000);
        }
    }
    else{
        $.notify("Welcome! Please read the instructions carefully. We are currently recruiting more people to join the room, once there are at least 3 users, the game will start. (click to close)", {autoHide: false, className: 'info'});
    }

    $('div.chatbox').scrollTop($('div.chatbox')[0].scrollHeight);

    var logged_users = [
        {'label': "@all",'id':'1'},
    ];
    {% for user in room_data.existing_users%}
        logged_users.push({'label': "@" + "{{user[0]}}", 'id': "{{user[1]}}"});
    {%endfor%}



    var autocomplete_options = {
        minLength: 1,
        position: { my : "right bottom", at: "right top" },
        autoFocus: true,
        source: function( request, response ) {
            // delegate back to autocomplete, but extract the last term
            var lastword = extractLast(request.term);
            if (lastword.length === 0){
                return;
            }
            // Regexp for filtering those labels that start with '@'
            var matcher = new RegExp( "^" + $.ui.autocomplete.escapeRegex(lastword) + '+', "i" );
            // Get all labels
            var labels = logged_users.map(function(item){return item.label;});
            var results = $.grep(labels, function( item ){
                             return matcher.test(item);
                        });
            response( $.ui.autocomplete.filter(results, lastword) );
        },
        focus: function() {
          // prevent value inserted on focus
          return false;
        },
        select: function( event, ui ) {
          var terms = split( this.value );
          // remove the current input
          terms.pop();
          // add the selected item
          terms.push( ui.item.value );
          // add placeholder to get the comma-and-space at the end
          terms.push("");
          this.value = terms.join(" ");
          return false;
        }
      };


    socket.on( 'connect', function() {
        var user_status = $('input#user_status').val();
        socket.emit('join', { 'room': room_id, 'user_name': user_name, 'user_status': user_status, user_type: current_user_type});
    });

    $('#leave_room').on('click', function(e){
        if (confirm('Are you sure you want to leave? Leaving the room will exclude you from participation.')) {
            var user_status = $('input#user_status').val();
            socket.emit('leave', { user_name: user_name, room: room_id, user_id:global_user_id, user_status: user_status, user_type: current_user_type});
            window.location.href = "/";
        }
    });

   $('#final_submit').on('click', function(e){
        if (confirm("Are you sure you want to Submit HIT? Press the button ONLY after you've submitted the solo solution, participated in the chat and submitted your final solution.")) {

            var mturk_url = $('#mturk_url').val();
            var selection = get_card_selection();
            var room_status = $('input#room_status').val();
            var user_status = $('input#user_status').val();

            socket.emit('response', {
                user_id: global_user_id,
                user_name: user_name,
                type: WASON_AGREE,
                message: selection,
                room: room_id,
                user_type: current_user_type,
                user_status: user_status
            });

            if (mturk_url != ''){
                $('#mturk').submit();
            }
        }
    });

    $('#group_start').on('click', function(e){
      $('#group_start').prop('disabled', true);
      socket.emit('response', { user_name: 'SYSTEM_MODERATOR', room: room_id, user_id: -1, user_status: USR_MODERATING, type: "MODERATION", message: "GROUP_PHASE_STARTED", user_type: current_user_type});
    });

    $('#group_ended').on('click', function(e){
      $('#group_ended').prop('disabled', true);
      socket.emit('response', { user_name: 'SYSTEM_MODERATOR', room: room_id, user_id: -1, user_status: USR_MODERATING, type: "MODERATION", message: "GROUP_PHASE_ENDED", user_type: current_user_type});
    });

    $('.kick').on('click', function(e){
        e.preventDefault();
        if (confirm('Are you sure you want kick this user?.')) {

            kick_user_id = $(this).val();
            kick_user_name = $(this).attr('name');
            kick_generic(kick_user_id, kick_user_name, room_id, true);
        }
    });

    var user_status = $('input#user_status').val();

    if (user_status == USR_MODERATING){
        $('#chat_container').removeClass('hidden');
    }

    $('#delibot_annotation').change(function(){
        $('#message').prop('disabled', false);
        $('#msg_submit').prop('disabled', false)
    });

    $('form#chat_form').on('submit', function(e) {
        var user_status = $('input#user_status').val();
        e.preventDefault();
        var message = $('input#message').val();
        var annotation = $('#delibot_annotation').val();

        if (message!=""){
            socket.emit( 'response', {
                user_id: global_user_id,
                user_name: user_name,
                type: CHAT_MESSAGE,
                message: {'message': message, 'annotation': annotation},
                room: room_id,
                user_type: current_user_type,
                user_status: user_status
          });
        }

        if (current_user_type == 'human_delibot'){

            $('#message').prop('disabled', true);
            $('#msg_submit').prop('disabled', true)
            $('#delibot_annotation').val('def');
        }

        $('input#message').val('').focus();

     });


    var card_click = $('input:checkbox').on('change', function(e){
        var selection = get_card_selection();
        var user_status = $('input#user_status').val();
        socket.emit( 'response', {
            user_id: global_user_id,
            user_name: user_name,
            type: WASON_GAME,
            message: selection,
            user_status: user_status,
            room: room_id,
            user_type: current_user_type
        });

        $('#btn-agree').prop('disabled', false);
    });


    var agree_clicked = $('#btn-agree').on('click', function(e){

        $('#btn-agree').text('Revise Solution')

        var selection = get_card_selection();
        room_status = $('input#room_status').val();
        var user_status = $('input#user_status').val();

        socket.emit('response', {
            user_id: global_user_id,
            user_name: user_name,
            type: WASON_AGREE,
            message: selection,
            room: room_id,
            user_type: current_user_type,
            user_status: user_status
        });

        if (user_status == USR_ONBOARDING){
            $.notify("Thank you for submitting your solution. The game will start soon! Please wait for the other participants to submit their solo selections. (click to close)", {autoHide: false, className: 'info'});
        }
        $('#btn-agree').prop('disabled', true);

    });

    $('.DELIBOT').on('click', function(e){
        id_type = e.target.id
        socket.emit('delibot', { room_id: room_id, delitype: id_type});
    });

    socket.on('response', function(message_str) {
        msg =  JSON.parse(message_str);
        console.log(msg);
        switch(msg.type) {
            case CHAT_MESSAGE:
                if(typeof msg.user_name !== 'undefined' ) {
                        local_name = msg.user_name;
                        local_id = msg.user_id;
                        processed_message = boldMentions(msg.message.message);
                        if (local_id == global_user_id){
                            $( 'div.chatbox' ).append('<div class="message msg-mine"><b>' + local_name +': </b> ' + processed_message +'</div>' );
                        }else{
                            $( 'div.chatbox' ).append('<div class="message msg-other"><b>' + local_name +': </b> ' + processed_message + '</div>');
                        }
                        $('div.chatbox').scrollTop($('div.chatbox')[0].scrollHeight);
                    }
                break;
            case JOIN_ROOM:
               var user_status = $('input#user_status').val()

               if (user_status == USR_MODERATING){
                    $("#current_users").append("<div class='logged_user' id='" + msg.user_id + "'><b>" + msg.user_name + "</b> <button class='btn btn-danger btn-sm kick' value='" + msg.user_id + "' name='" + msg.user_name + "'>Kick user</button></div>");
                    $('.kick').on('click', function(e){
                        e.preventDefault();
                        var user_id = $(this).val();
                        var user_name = $(this).attr('name')
                        socket.emit('leave', { user_name: user_name, room: room_id, user_id: user_id, user_status: 'KICKED', user_type: current_user_type});

                        $('#'+user_id).remove();
                        logged_users = logged_users.filter(function(el) { return el.label != "@"+user_name; });
                        $("#message").bind("keydown", function( event ) {
                            if (event.keyCode === $.ui.keyCode.TAB &&
                                $(this).autocomplete("instance").menu.active ) {
                              event.preventDefault();
                            }
                        }).autocomplete(autocomplete_options);
                    });
               }
               else{
                   $("#current_users").append("<div class='logged_user' id='" + msg.user_id + "'><b>" + msg.user_name + "</b></div>");
               }

                logged_users.push({'label': "@" + msg.user_name,'id': msg.user_id})
                $("#message").bind("keydown", function(event){
                    if (event.keyCode === $.ui.keyCode.TAB &&
                        $(this).autocomplete("instance").menu.active ) {
                      event.preventDefault();
                    }
                  }).autocomplete(autocomplete_options);
                break;
            case LEAVE_ROOM:
                console.log("triggered leave room: " + msg)

                $('#'+msg.user_id).remove();
                logged_users = logged_users.filter(function(el) { return el.label != "@"+msg.user_name; });
                $("#message").bind("keydown", function( event ) {
                    if (event.keyCode === $.ui.keyCode.TAB &&
                        $(this).autocomplete("instance").menu.active ) {
                      event.preventDefault();
                    }
                }).autocomplete(autocomplete_options);
                if (msg.user_id == global_user_id){
                    window.location.href = "/";
                }
                break;
            case WASON_FINISHED:
                $('.task button').prop('disabled', true);
                $('.task input').prop('disabled', true);
                $('.timer_holder').addClass('hidden');
                $.notify("Game Finished! Thank you for playing! (click to close)", {autoHide: false, className: 'success'});
                $('input#room_status').val('GAME_FINISHED');
                $(window).scrollTop(0);
                break;
            case WASON_AGREE:
                target_user_id = msg.user_id;
                //$('#' + target_user_id).addClass('wason-agreed');
                break;
            case ROUTING_TIMER_STARTED:
                $.notify("The group phase of the game will start soon! Please submit your card selection. Once everyone does so, the game will start! (click to close)", {autoHide: false, className: 'info'});
                sound.play()
                var date = msg.message;

                $('#game_start_timer').removeClass('hidden');

                var now = new Date();
                var after_x_min = new Date(now);
                after_x_min.setMinutes(now.getMinutes() + parseInt(date));
                var countDownDate = after_x_min.getTime();

                var selection = get_card_selection();
                var user_status = $('input#user_status').val()
                var timer = setInterval(function(){start_timer(countDownDate, true, "Waiting for player", function(){
                    socket.emit('response', {
                            user_id: global_user_id,
                            user_name: user_name,
                            type: ROUTING_TIMER_ELAPSED,
                            room: room_id,
                            user_status: user_status,
                            message: selection,
                            user_type: current_user_type
                        });
                    clearInterval(timer);
                })}, 1000);

                activityWatcher(wakeup, kick);
                break;
            case ROUTING_TIMER_ELAPSED:
                $('input#room_status').val(READY_TO_START);
                break;
            case FINISHED_ONBOARDING:
                $('.logged_user').removeClass('wason-agreed');
                $('input#user_status').val(USR_PLAYING);
                $('#btn-agree').prop('disabled', false);

                var room_status = $('input#room_status').val()

                if (room_status != ROOM_PLAYING){
                    sound.play()
                    $.notify('Now you have to collaborate with the other participants in this conversation to solve the task together. (click to close)',  {autoHide: false, className: 'info'});
                }
                clearInterval(timer);
                $('#chat_container').removeClass('hidden');
                $('#game_play_timer').removeClass('hidden');
                $('.task_description').removeClass('hidden');
                $('#game_start_timer').addClass('hidden');

                var date = msg.message;
                var now = new Date();
                var after_x_min = new Date(now);
                after_x_min.setMinutes (now.getMinutes() + date);
                var countDownDate = after_x_min.getTime()

                clearInterval(timer);
                var timer = setInterval(function(){start_timer(countDownDate, true, "Out of time", function(){
                        $('#timer').text("Out of time");
                        var selection = get_card_selection();
                        var user_status = $('input#user_status').val()
                        socket.emit('response', {
                            user_id: global_user_id,
                            user_name: user_name,
                            type: 'OUT_OF_TIME',
                            message: selection,
                            room: room_id,
                            user_status: user_status,
                            user_type: current_user_type
                        })
                        clearInterval(timer);
                        ;})}, 1000);
                $('input#room_status').val(ROOM_PLAYING);

                break;
            default:
                break;
            // code block
        }
    });

    $("#message").bind("keydown", function( event ) {
        if (event.keyCode === $.ui.keyCode.TAB &&
            $(this).autocomplete("instance").menu.active ) {
          event.preventDefault();
        }
      }).autocomplete(autocomplete_options);


    $(window).on('mouseover', (function () {
        window.onbeforeunload = null;
    }));
    $(window).on('mouseout', (function () {
        window.onbeforeunload = Leave;
    }));

    function Leave() {
        var user_status = $('input#user_status').val();

        socket.emit('leave', { user_name: user_name, room: room_id, user_id:global_user_id, user_status: user_status, user_type: current_user_type});
    }

    function kick(){
        status = $('input#room_status').val();
        if(status != 'GAME_FINISHED'){
            kick_generic(global_user_id, user_name, room_id);
        }
    }

    function wakeup(){
        status = $('input#room_status').val();
        if(status != 'GAME_FINISHED'){
            sound.play();
            $.notify("You have been inactive for a while. Please be mindful, that after a prolonged period of inactivity you will be excluded from the room. (click to close)", {autoHide: false, className: 'error'});
        }
    }

    function kick_generic(user_id, user_name, room_id, is_moderator=false){
        socket.emit('leave', { user_name: user_name, room: room_id, user_id: user_id, user_status: 'KICKED'});
        $('#'+user_id).remove();
        logged_users = logged_users.filter(function(el) { return el.label != "@"+user_name; });
        $("#message").bind("keydown", function( event ) {
            if (event.keyCode === $.ui.keyCode.TAB &&
                $(this).autocomplete("instance").menu.active ) {
              event.preventDefault();
            }
        }).autocomplete(autocomplete_options);

        if (is_moderator != true){
            window.location.href = "/";
        }
    }
    var prevKey="";
    $(document).keydown(function (e) {
        if (e.key=="F5") {
            window.onbeforeunload = Leave;
        }
        else if (e.key.toUpperCase() == "W" && prevKey == "CONTROL") {
            window.onbeforeunload = Leave;
        }
        else if (e.key.toUpperCase() == "R" && prevKey == "CONTROL") {
            window.onbeforeunload = Leave;
        }
        else if (e.key.toUpperCase() == "F4" && (prevKey == "ALT" || prevKey == "CONTROL")) {
            window.onbeforeunload = Leave;
        }
        prevKey = e.key.toUpperCase();
    });
});